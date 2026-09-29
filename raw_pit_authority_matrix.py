"""Use-specific RAW_AS_TRADED / POINT_IN_TIME authority matrix (PROSPECTIVE_RAW_PIT_AUTHORITY_V1).

Ten dimensions, never collapsed into one boolean. ``BEFORE`` is the repository's recorded state at
canonical main ac9b8cf (docs/STATE.md Invariant 1, ROADMAP_STATE ``RAW_AS_TRADED_AND_HISTORICAL_PIT``,
``historical_pit_raw_as_traded_evidence`` OUTCOME_D). ``evaluate`` derives ``AFTER`` from measured
evidence counts only, and types every remaining blocker as engineering-creatable, future-calendar-time,
or external source/permission. A dimension is promoted only inside the scope its counts earn.
"""
from __future__ import annotations

from typing import Any, Mapping

CONTRACT_VERSION = "raw_pit_authority_matrix/v1"

DIMENSIONS = (
    "CURRENT_SESSION_PRICE_RESEARCH", "PROSPECTIVE_AS_KNOWN_PRICE_EVIDENCE", "PROSPECTIVE_RAW_AS_TRADED_PRICE",
    "HISTORICAL_RAW_AS_TRADED_PRICE", "CORPORATE_ACTION_EVENT_AUTHORITY", "CORPORATE_ACTION_FACTOR_CHAIN",
    "POINT_IN_TIME_ADJUSTED_HISTORY", "RETROSPECTIVE_ADJUSTED_RESEARCH_HISTORY", "PIT_BACKTEST_ELIGIBILITY",
    "EXECUTION_REPLAY_ELIGIBILITY",
)

BEFORE = {
    "CURRENT_SESSION_PRICE_RESEARCH": "DESCRIPTIVE_QUALIFIED_ONLY",
    "PROSPECTIVE_AS_KNOWN_PRICE_EVIDENCE": "EXPERIMENT_SHADOW_ONLY",
    "PROSPECTIVE_RAW_AS_TRADED_PRICE": "NOT_PROMOTED",
    "HISTORICAL_RAW_AS_TRADED_PRICE": "NOT_PROMOTED",
    "CORPORATE_ACTION_EVENT_AUTHORITY": "EX_DATE_UNQUALIFIED_OUTCOME_D",
    "CORPORATE_ACTION_FACTOR_CHAIN": "BLOCKED",
    "POINT_IN_TIME_ADJUSTED_HISTORY": "BLOCKED",
    "RETROSPECTIVE_ADJUSTED_RESEARCH_HISTORY": "RESEARCH_ONLY_ADJUSTED_RETROSPECTIVE",
    "PIT_BACKTEST_ELIGIBILITY": "BLOCKED",
    "EXECUTION_REPLAY_ELIGIBILITY": "BLOCKED",
}


def _blocker(missing: str, *, engineering: bool, future_time: bool, external: bool, note: str = "") -> dict[str, Any]:
    return {"missing_evidence": missing, "engineering_can_create": engineering,
            "only_future_calendar_time_can_create": future_time, "external_permission_or_data_required": external, "note": note}


def evaluate(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """``evidence`` carries measured counts (see tools/run_prospective_raw_pit_authority.py)."""
    e = evidence
    after: dict[str, dict[str, Any]] = {}

    prospective_bars = int(e.get("prospective_dnse_bars", 0))
    cross_agreed = int(e.get("prospective_raw_qualified_bars", 0))
    after["CURRENT_SESSION_PRICE_RESEARCH"] = {
        "state": "QUALIFIED_WITH_PROSPECTIVE_LINEAGE" if prospective_bars and e.get("same_session_cross_source_agreement_09_28", 0) else "DESCRIPTIVE_QUALIFIED_ONLY",
        "scope": "exact-session bars linked to a hashed known-time receipt; official HOSE agreement on the latest session",
        "blockers": [],
    }
    after["PROSPECTIVE_AS_KNOWN_PRICE_EVIDENCE"] = {
        "state": "OPERATIONAL" if e.get("prospective_sessions", 0) >= 20 and prospective_bars else "BLOCKED",
        "scope": f"{e.get('prospective_sessions', 0)} retained sessions, {prospective_bars} post-close same-session bars; "
                 "possession at known time only, not a never-revised claim",
        "blockers": [_blocker("automated Daily wiring of the receipt manifest", engineering=True, future_time=False, external=False,
                              note="component-local hook added; Daily never fails on it")],
    }
    after["PROSPECTIVE_RAW_AS_TRADED_PRICE"] = {
        "state": "QUALIFIED_SCOPED_CROSS_SOURCE" if cross_agreed else "BLOCKED",
        "scope": f"{cross_agreed} DNSE post-close bars whose values equal the official HOSE series (empirically unadjusted); "
                 "HOSE-listed tickers only; HNX/UPCoM stay as-known-only (bulk acquisition not authorized)",
        "blockers": [_blocker("independent official series for HNX/UPCoM", engineering=False, future_time=False, external=True,
                              note="HNX written permission or information-service agreement")],
    }
    depth = int(e.get("hose_event_tests_unadjusted", 0))
    after["HISTORICAL_RAW_AS_TRADED_PRICE"] = {
        "state": "PARTIAL_HOSE_EMPIRICAL_SCOPED" if depth >= 2 else "BLOCKED",
        "scope": f"HOSE tradingresult series retained for {e.get('hose_tickers', 0)} tickers; empirically unadjusted across "
                 f"{depth} tested events; research grade only (basis undocumented by the source)",
        "blockers": [
            _blocker("documented raw basis statement from HOSE", engineering=False, future_time=False, external=True),
            _blocker("HNX/UPCoM and pre-retention DNSE history", engineering=False, future_time=False, external=True,
                     note="information loss for pre-2026-08-20 non-HOSE sessions, not engineering debt"),
        ],
    }
    ex_dates = int(e.get("explicit_ex_date_events", 0))
    after["CORPORATE_ACTION_EVENT_AUTHORITY"] = {
        "state": "PARTIAL_EX_DATE_QUALIFIED_TERMS_AND_PUBLICATION_TIME_MISSING" if ex_dates else BEFORE["CORPORATE_ACTION_EVENT_AUTHORITY"],
        "scope": f"{ex_dates} official events with an explicit ex-date (HNX rights event index, retained 2026-09-05); "
                 f"{e.get('ratio_or_cash_terms_events', 0)} carry ratio/cash terms; {e.get('publication_time_events', 0)} carry publication time",
        "blockers": [
            _blocker("ratio / cash amount / issue terms per event", engineering=True, future_time=False, external=False,
                     note="official announcement documents must be acquired and parsed"),
            _blocker("publication (knowledge) time of each announcement", engineering=False, future_time=True, external=False,
                     note="only prospective retention at publication time creates it"),
            _blocker("HOSE-listed event calendar", engineering=True, future_time=False, external=False,
                     note="retained index covers HNX/UPCoM; HOSE tickers have 69 events"),
        ],
    }
    chain = int(e.get("qualified_factor_chain_events", 0))
    after["CORPORATE_ACTION_FACTOR_CHAIN"] = {
        "state": "QUALIFIED_BOUNDED" if chain else "BLOCKED",
        "scope": f"{chain} qualified events",
        "blockers": [] if chain else [
            _blocker("official terms + explicit ex-date + executed-lifecycle evidence + publication cutoff for one event",
                     engineering=True, future_time=True, external=False,
                     note="observed re-basing ratios are consistency evidence only and are never used as the factor"),
        ],
    }
    after["POINT_IN_TIME_ADJUSTED_HISTORY"] = {
        "state": "QUALIFIED_BOUNDED" if chain else "BLOCKED",
        "scope": "contract and readiness only (pit_price_reconstruction_contract); needs a qualified factor chain",
        "blockers": [] if chain else [_blocker("qualified factor chain versioned by knowledge time", engineering=True, future_time=True, external=False)],
    }
    after["RETROSPECTIVE_ADJUSTED_RESEARCH_HISTORY"] = {
        "state": "RESEARCH_ONLY_ADJUSTED_RETROSPECTIVE",
        "scope": f"DNSE series re-fetched later is re-based after the fact: {e.get('official_verified_rebasing_pairs', 0)} bar pairs where the "
                 f"unadjusted official series equals the value known at T0; {e.get('t0_bar_not_final_pairs', 0)} same-day bars were later found non-final; "
                 "never labelled raw or point-in-time",
        "blockers": [],
    }
    after["PIT_BACKTEST_ELIGIBILITY"] = {
        "state": "BLOCKED", "scope": "requires factor chain, PIT universe (ACTIVE_UNIVERSE UNKNOWN), PIT features and history depth",
        "blockers": [
            _blocker("PIT-qualified universe membership (ACTIVE_UNIVERSE)", engineering=False, future_time=False, external=True,
                     note="official listing-status route, not another cohort widening"),
            _blocker("sufficient prospective history depth", engineering=False, future_time=True, external=False),
            _blocker("qualified factor chain", engineering=True, future_time=True, external=False),
        ],
    }
    after["EXECUTION_REPLAY_ELIGIBILITY"] = {
        "state": "BLOCKED", "scope": "execution capacity/sizing policy and tick-level raw trades not established",
        "blockers": [
            _blocker("participation-rate, days-to-liquidate and market-impact policy", engineering=True, future_time=False, external=False),
            _blocker("complete historical trade ticks", engineering=False, future_time=False, external=True,
                     note="local corpus holds only page-capped samples; completeness unprovable"),
        ],
    }
    return {"contract_version": CONTRACT_VERSION, "dimensions": list(DIMENSIONS), "before": dict(BEFORE), "after": after,
            "changed": [d for d in DIMENSIONS if after[d]["state"] != BEFORE[d]]}
