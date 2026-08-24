"""Current official exchange-master projection over retained Stock Lookup evidence.

The projection is deliberately a *current* identity boundary.  It is not a
historical constituent file, a common-share source, or an instruction to add
official-only rows to the production candidate universe.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from typing import Any, Mapping


CONTRACT_VERSION = "current_official_market_universe/v1"
OFFICIAL_CURRENT_EXCHANGE_SECURITY = "OFFICIAL_CURRENT_EXCHANGE_SECURITY"
OFFICIAL_CURRENT_STOCK_LIST_CANDIDATE = "OFFICIAL_CURRENT_STOCK_LIST_CANDIDATE"
STOCKLOOKUP_ONLY_UNRESOLVED = "STOCKLOOKUP_ONLY_UNRESOLVED"
OFFICIAL_ONLY_NOT_IN_STOCKLOOKUP = "OFFICIAL_ONLY_NOT_IN_STOCKLOOKUP"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _identity(artifact: Mapping[str, Any]) -> dict[str, str]:
    payload = copy.deepcopy(dict(artifact))
    payload.pop("artifact_sha256", None)
    payload.pop("artifact_identity", None)
    digest = hashlib.sha256(_canonical(payload)).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"current_official_market_universe:{digest}"}


def _verify(artifact: Mapping[str, Any], label: str) -> None:
    payload = copy.deepcopy(dict(artifact))
    digest = payload.pop("artifact_sha256", None)
    identity = payload.pop("artifact_identity", None)
    expected = hashlib.sha256(_canonical(payload)).hexdigest()
    if digest != expected or not isinstance(identity, str) or not identity.endswith(expected):
        raise ValueError(f"{label}_IDENTITY_MISMATCH")


def _rows(artifact: Mapping[str, Any], dataset: str) -> list[Mapping[str, Any]]:
    rows = artifact.get("datasets", {}).get(dataset)
    if not isinstance(rows, list):
        raise ValueError(f"DATASET_MISSING:{dataset}")
    return rows


def _by_ticker(rows: list[Mapping[str, Any]], label: str) -> dict[str, Mapping[str, Any]]:
    output: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker or ticker in output:
            raise ValueError(f"{label}_TICKER_DUPLICATE_OR_MISSING")
        output[ticker] = row
    return output


def _observed_by_source(artifact: Mapping[str, Any]) -> dict[str, str | None]:
    captures = artifact.get("captures", [])
    if not isinstance(captures, list):
        raise ValueError("CAPTURES_INVALID")
    return {str(capture.get("sha256")): capture.get("retrieved_at") for capture in captures if capture.get("sha256")}


def _source_row(*, row: Mapping[str, Any], source: str, observed_at: str | None) -> dict[str, Any]:
    ticker = str(row["ticker"]).upper()
    if source == "HNX_UPCOM":
        return {
            "ticker": ticker, "issuer_name": row.get("issuer_name"), "exchange_or_market": row.get("market"),
            "official_source": "hnx_official_equity_universe/v1", "official_source_row_identity": f"{row.get('source_identity')}:{ticker}",
            "official_observed_at": observed_at, "first_trading_date": row.get("first_trading_date"),
            "instrument_class_status": "EXCHANGE_STOCK_LIST_CANDIDATE_NOT_COMMON_EQUITY_PROVEN",
            "current_universe_status": OFFICIAL_CURRENT_STOCK_LIST_CANDIDATE,
            "qualification": "FIRST_PARTY_CURRENT_HNX_OR_UPCOM_STOCK_LIST_ROW",
            "warnings": ["HNX list evidence establishes current exchange-list presence, not accounting common shares outstanding."],
        }
    return {
        "ticker": ticker, "issuer_name": row.get("issuer_name"), "exchange_or_market": "HOSE",
        "official_source": "hose_public_stock_master/v1", "official_source_row_identity": f"{row.get('source_identity')}:{row.get('hose_security_id')}:{ticker}",
        "official_observed_at": observed_at, "first_trading_date": None,
        "instrument_class_status": "OFFICIAL_STOCK_MASTER_SECURITY_TYPE_NOT_COMMON_EQUITY_PROVEN",
        "current_universe_status": OFFICIAL_CURRENT_EXCHANGE_SECURITY,
        "qualification": "FIRST_PARTY_CURRENT_HOSE_STOCK_MASTER_ROW",
        "warnings": ["HOSE outStanding is retained only as exchange-labelled outstanding volume, not common shares outstanding."],
    }


def _consumer_counts(records: Mapping[str, Any], eligible: set[str], kind: str) -> dict[str, int]:
    scoped = [records[ticker] for ticker in eligible]
    if kind == "screening":
        ready = sum(row.get("market_relative_comparison", {}).get("status") == "AVAILABLE" for row in scoped)
        return {"candidate_denominator": len(scoped), "data_ready": ready, "data_limited": len(scoped) - ready}
    if kind == "tactical":
        ready = sum(row.get("entry_state") is not None for row in scoped)
        return {"candidate_denominator": len(scoped), "classified": ready, "data_limited": len(scoped) - ready}
    if kind == "strategy":
        ready = sum(bool(row.get("eligible_strategy_ids")) for row in scoped)
        return {"candidate_denominator": len(scoped), "eligible": ready, "data_limited": len(scoped) - ready}
    if kind == "scenario":
        states = Counter(row.get("scenario_disposition", "SCENARIO_INSUFFICIENT_DATA") for row in scoped)
        return {"candidate_denominator": len(scoped), "ready": states["SCENARIO_READY"], "partial": states["SCENARIO_PARTIAL"], "insufficient": states["SCENARIO_INSUFFICIENT_DATA"]}
    raise ValueError(f"UNKNOWN_CONSUMER:{kind}")


def _breadth_counts(records: Mapping[str, Any], scope: set[str]) -> dict[str, int]:
    values = []
    for ticker in scope:
        technical = records[ticker].get("technical_features", {})
        value = technical.get("values", {}).get("return_1d")
        if technical.get("is_current_session") and isinstance(value, (int, float)):
            values.append(value)
    return {"advancers": sum(value > 0 for value in values), "decliners": sum(value < 0 for value in values),
            "unchanged": sum(value == 0 for value in values), "same_session_breadth_observed": len(values)}


def build_artifact(*, hnx: Mapping[str, Any], hose: Mapping[str, Any], status: Mapping[str, Any], descriptive: Mapping[str, Any], screening: Mapping[str, Any], tactical: Mapping[str, Any], strategy: Mapping[str, Any], scenario: Mapping[str, Any]) -> dict[str, Any]:
    """Reconcile retained master rows and quantify compatible existing consumers."""
    for label, artifact in (("HNX", hnx), ("HOSE", hose), ("STATUS", status), ("DESCRIPTIVE", descriptive), ("SCREENING", screening), ("TACTICAL", tactical), ("STRATEGY", strategy), ("SCENARIO", scenario)):
        _verify(artifact, label)
    hnx_rows = _by_ticker(_rows(hnx, "hnx_official_equity_universe/v1"), "HNX")
    hose_rows = _by_ticker(_rows(hose, "hose_public_stock_master/v1"), "HOSE")
    hnx_observed, hose_observed = _observed_by_source(hnx), _observed_by_source(hose)
    if set(hnx_rows) & set(hose_rows):
        raise ValueError("OFFICIAL_EXCHANGE_TICKER_CONFLICT")
    candidates = status.get("records")
    if not isinstance(candidates, Mapping) or len(candidates) != 1683:
        raise ValueError("STOCKLOOKUP_1683_CANDIDATE_CONTRACT_INVALID")
    for label, artifact in (("DESCRIPTIVE", descriptive), ("SCREENING", screening), ("TACTICAL", tactical), ("STRATEGY", strategy), ("SCENARIO", scenario)):
        if set(artifact.get("records", {})) != set(candidates):
            raise ValueError(f"{label}_CANDIDATE_SET_MISMATCH")

    official = {**hnx_rows, **hose_rows}
    candidate_tickers = set(candidates)
    records: dict[str, dict[str, Any]] = {}
    residuals = Counter()
    for ticker in sorted(candidate_tickers | set(official)):
        stocklookup_record = candidates.get(ticker)
        if ticker in hnx_rows:
            record = _source_row(row=hnx_rows[ticker], source="HNX_UPCOM", observed_at=hnx_observed.get(str(hnx_rows[ticker].get("source_identity"))))
        elif ticker in hose_rows:
            record = _source_row(row=hose_rows[ticker], source="HOSE", observed_at=hose_observed.get(str(hose_rows[ticker].get("source_identity"))))
        else:
            prior = stocklookup_record or {}
            state = prior.get("activity_and_session_state")
            if state == "INACTIVE_OR_DELISTED":
                residual = "DELISTED_OR_NO_LONGER_CURRENT"
            elif state in {"ACTIVE_LISTED_OBSERVED", "ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION"}:
                residual = "SYMBOL_IDENTITY_DRIFT"
            else:
                residual = "UNRESOLVED"
            residuals[residual] += 1
            record = {"ticker": ticker, "issuer_name": None, "exchange_or_market": prior.get("vci_exchange_reference"),
                      "official_source": None, "official_source_row_identity": None, "official_observed_at": None,
                      "first_trading_date": None, "instrument_class_status": "INSTRUMENT_CLASS_UNRESOLVED",
                      "current_universe_status": STOCKLOOKUP_ONLY_UNRESOLVED, "qualification": residual,
                      "warnings": ["No matching retained current HNX/UPCoM or HOSE master row; absence is not zero or proof of instrument class."]}
        record["stocklookup_candidate"] = stocklookup_record is not None
        if not stocklookup_record:
            record["current_universe_status"] = OFFICIAL_ONLY_NOT_IN_STOCKLOOKUP
            record["qualification"] = "CANDIDATE_UNIVERSE_STALENESS_OR_GOVERNED_EXCLUSION_UNRESOLVED"
            record["warnings"].append("Official-only row is retained for owner review and is not automatically added to Stock Lookup.")
        records[ticker] = record
    if len(records) != len(set(records)):
        raise ValueError("PROJECTION_TICKER_DUPLICATE")

    eligible = {ticker for ticker, row in records.items() if row["stocklookup_candidate"] and row["current_universe_status"] in {OFFICIAL_CURRENT_EXCHANGE_SECURITY, OFFICIAL_CURRENT_STOCK_LIST_CANDIDATE}}
    previous_active = {ticker for ticker, row in candidates.items() if row.get("activity_and_session_state") in {"ACTIVE_LISTED_OBSERVED", "ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION"}}
    observed = {ticker for ticker, row in candidates.items() if row.get("activity_and_session_state") == "ACTIVE_LISTED_OBSERVED"}
    # The prior descriptive breadth output is current-session technical only; preserve its formula and scope.
    before_breadth_counts = _breadth_counts(descriptive["records"], previous_active)
    after_breadth_counts = _breadth_counts(descriptive["records"], eligible)
    breadth_before = {"denominator": len(previous_active), "observed_tickers": len(observed), "missing_market_observations": len(previous_active - observed), **before_breadth_counts,
                      "advance_ratio": before_breadth_counts["advancers"] / (before_breadth_counts["advancers"] + before_breadth_counts["decliners"]), "coverage_ratio": len(observed) / len(previous_active)}
    breadth_after = {"denominator": len(eligible), "observed_tickers": len(observed & eligible), "missing_market_observations": len(eligible - observed), **after_breadth_counts,
                     "advance_ratio": after_breadth_counts["advancers"] / (after_breadth_counts["advancers"] + after_breadth_counts["decliners"]), "coverage_ratio": len(observed & eligible) / len(eligible)}
    before = {"candidate_denominator": len(candidate_tickers)}
    after = {"candidate_denominator": len(eligible), "excluded_by_official_universe": len(candidate_tickers - eligible), "unresolved_identity": sum(records[t]["current_universe_status"] == STOCKLOOKUP_ONLY_UNRESOLVED for t in candidate_tickers)}
    consumer = {
        "breadth": {"before": breadth_before, "after": breadth_after, "fitness": "FIT_CURRENT_DESCRIPTIVE_DENOMINATOR_WITH_EXPLICIT_PARTIAL_COVERAGE"},
        "screening": {"before": {**before, **_consumer_counts(screening["records"], candidate_tickers, "screening")}, "after": {**after, **_consumer_counts(screening["records"], eligible, "screening")}, "fitness": "FIT_VIA_TICKER_FILTER_ADAPTER_CURRENT_RESEARCH_ONLY"},
        "tactical": {"before": _consumer_counts(tactical["records"], candidate_tickers, "tactical"), "after": _consumer_counts(tactical["records"], eligible, "tactical"), "fitness": "FIT_VIA_TICKER_FILTER_ADAPTER_NO_RULE_CHANGE"},
        "strategy": {"before": _consumer_counts(strategy["records"], candidate_tickers, "strategy"), "after": _consumer_counts(strategy["records"], eligible, "strategy"), "fitness": "FIT_VIA_TICKER_FILTER_ADAPTER_NO_RULE_CHANGE"},
        "scenario": {"before": _consumer_counts(scenario["records"], candidate_tickers, "scenario"), "after": _consumer_counts(scenario["records"], eligible, "scenario"), "fitness": "FIT_VIA_TICKER_FILTER_ADAPTER_NO_ARCHITECTURE_CHANGE"},
        "daily_research": {"before_candidate_denominator": len(candidate_tickers), "after_candidate_denominator": len(eligible), "adapter": "records[ticker].current_universe_status ticker-filter; existing daily records remain immutable", "fitness": "FIT_VIA_EXPLICIT_TICKER_FILTER_ADAPTER_CURRENT_RESEARCH_ONLY"},
    }
    events = _rows(hnx, "hnx_official_rights_event_index/v1")
    event_tickers = sorted({str(event.get("ticker")).upper() for event in events if event.get("qualification") == "EX_DATE_OFFICIAL_QUALIFIED" and str(event.get("ticker")).upper() in eligible})
    artifact = {"schema_version": "1.0.0", "contract_version": CONTRACT_VERSION,
        "source_artifact_identities": {"hnx": hnx["artifact_identity"], "hose": hose["artifact_identity"], "status": status["artifact_identity"], "descriptive": descriptive["artifact_identity"], "screening": screening["artifact_identity"], "tactical": tactical["artifact_identity"], "strategy": strategy["artifact_identity"], "scenario": scenario["artifact_identity"]},
        "records": records,
        "reconciliation": {"stocklookup_universe_count": len(candidate_tickers), "official_hnx_upcom_match": len(candidate_tickers & set(hnx_rows)), "official_hose_match": len(candidate_tickers & set(hose_rows)), "official_total_match": len(eligible), "stocklookup_only_unresolved": len(candidate_tickers - eligible), "official_only_not_in_stocklookup": len(set(official) - candidate_tickers), "identity_conflicts": 0,
                           "residual_disposition": {"DELISTED_OR_NO_LONGER_CURRENT": residuals["DELISTED_OR_NO_LONGER_CURRENT"], "NON_COMMON_SECURITY": residuals["NON_COMMON_SECURITY"], "OTHER_MARKET_OR_UNSUPPORTED": residuals["OTHER_MARKET_OR_UNSUPPORTED"], "SYMBOL_IDENTITY_DRIFT": residuals["SYMBOL_IDENTITY_DRIFT"], "UNRESOLVED": residuals["UNRESOLVED"]},
                           "official_only_tickers": sorted(set(official) - candidate_tickers)},
        "fitness_for_use": {"CURRENT_MARKET_BREADTH_DENOMINATOR": "FIT_CURRENT_OFFICIAL_EXCHANGE_PRESENCE_WITH_PARTIAL_SESSION_COVERAGE", "CURRENT_SCREENING_CANDIDATE_DENOMINATOR": "FIT_VIA_EXPLICIT_FILTER", "CURRENT_STRATEGY_CLASSIFICATION_CANDIDATE": "FIT_VIA_EXPLICIT_FILTER", "CURRENT_DAILY_RESEARCH_CANDIDATE": "FIT_VIA_EXPLICIT_FILTER", "HISTORICAL_PIT_UNIVERSE": "BLOCKED_NOT_CONSTRUCTED", "SURVIVORSHIP_SAFE_BACKTEST_UNIVERSE": "BLOCKED_NOT_CONSTRUCTED"},
        "consumer_compatibility": consumer,
        "event_context_linkage": {"status": "EVENT_DATA_READY_CONSUMER_MAPPING_PENDING", "qualified_event_tickers": event_tickers, "mapping": "HNX qualified ex-date rows retain ticker/source identity and can map to Corporate Intelligence EVENT_FIELDS; no existing CI loader accepts this dataset without an explicit adapter.", "authority_boundary": "EX_DATE_EVIDENCE_ONLY_NO_PRICE_ADJUSTMENT_RAW_AS_TRADED_OR_EVENT_OUTCOME_PROMOTION"},
        "authority_boundary": "CURRENT_OFFICIAL_EXCHANGE_PRESENCE_ONLY; NOT_COMMON_SHARE_AUTHORITY; NOT_HISTORICAL_PIT; NOT_SURVIVORSHIP_SAFE; NO_RANKING_SIZING_EXECUTION_OR_AUTOMATIC_CANDIDATE_ADDITION", "missing_is_zero": False, "canonical_store_mutated": False, "production_db_written": False}
    artifact.update(_identity(artifact)); return artifact


def replay(artifact: Mapping[str, Any]) -> None:
    _verify(artifact, "CURRENT_OFFICIAL_MARKET_UNIVERSE")
    records = artifact.get("records", {})
    if len(records) != len(set(records)) or len(set(records)) < 1683:
        raise ValueError("PROJECTION_RECORD_ACCOUNTING_INVALID")
    reconciliation = artifact.get("reconciliation", {})
    if reconciliation.get("official_total_match", 0) + reconciliation.get("stocklookup_only_unresolved", 0) != reconciliation.get("stocklookup_universe_count"):
        raise ValueError("STOCKLOOKUP_RECONCILIATION_INVALID")
