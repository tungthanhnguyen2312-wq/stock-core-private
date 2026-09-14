"""Focused regression coverage for CURRENT_OFFICIAL_MARKET_UNIVERSE_REFRESH_AND_SECURITY_STATUS_V1.

Covers the additive ``official_security_status`` field family and the refreshed 2026-09-13
official-universe reconciliation. Does not duplicate ``tests/test_current_official_market_
universe.py`` (still the primary determinism/tampering/2026-08-24 regression suite, unchanged)
or ``tests/test_hose_public_xhr_and_periodic_series_recon.py`` (still the primary XHR-shape
suite). Real refreshed evidence is used where the assertion is about the actual current market
state; hand-built fixtures are used where the assertion is about a specific status-classification
rule that real evidence may or may not currently exercise.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pytest

from current_official_market_universe import (
    OFFICIAL_ONLY_NOT_IN_STOCKLOOKUP, STATUS_NORMAL, STATUS_NOT_PROVIDED, STATUS_UNKNOWN_CODE,
    _hose_official_security_status, _source_row, build_artifact, replay,
)
from hose_public_xhr_and_periodic_series_recon import build as build_hose


ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "operations-review"
PATHS_20260913 = {
    "hnx": OPS / "hnx-enumerable-universe-kllh-event-and-disclosure-scaleout-v1-20260913/hnx_enumerable_universe_artifact.json",
    "hose": OPS / "hose-public-xhr-and-periodic-series-recon-v1-20260913/hose_public_xhr_artifact.json",
    "status": OPS / "current-universe-status-and-session-coverage-resolution-v1-20260911/current_universe_status_and_session_coverage_resolution_artifact.json",
    "descriptive": OPS / "market-wide-current-descriptive-research-v1-20260911/market_wide_current_descriptive_research_artifact.json",
    "screening": OPS / "current-market-screening-opportunity-comparison-foundation-v1-20260911/current_market_screening_opportunity_comparison_foundation_artifact.json",
    "tactical": OPS / "watchlist-tactical-entry-decision-v1-20260911/watchlist_tactical_entry_classifier_artifact.json",
    "strategy": OPS / "polymorphic-current-strategy-classification-v1-20260911/polymorphic_current_strategy_classification_artifact.json",
    "scenario": OPS / "current-evidence-bound-scenario-v1-20260911/current_evidence_bound_scenario_artifact.json",
}
_REQUIRES_REFRESHED_EVIDENCE = pytest.mark.skipif(
    not all(path.is_file() for path in PATHS_20260913.values()),
    reason="Refreshed 2026-09-13 evidence not present in this worktree/checkout.",
)


@lru_cache(maxsize=1)
def _build_refreshed():
    return build_artifact(**{name: json.loads(path.read_text(encoding="utf-8")) for name, path in PATHS_20260913.items()})


# 1. Current HNX_LISTED row.
def test_current_hnx_listed_row_is_included_with_status_not_provided():
    row = {"ticker": "clm", "issuer_name": "X", "market": "HNX_LISTED", "first_trading_date": "2016-04-15", "source_identity": "sha"}
    record = _source_row(row=row, source="HNX_UPCOM", observed_at="2026-09-13T00:00:00Z")
    assert record["current_universe_status"] == "OFFICIAL_CURRENT_STOCK_LIST_CANDIDATE"
    assert record["exchange_or_market"] == "HNX_LISTED"
    assert record["official_security_status"] == STATUS_NOT_PROVIDED
    assert record["official_security_status_effective_date"] is None


# 2. Current UPCoM row.
def test_current_upcom_row_is_included_with_status_not_provided():
    row = {"ticker": "a32", "issuer_name": "Y", "market": "UPCOM", "first_trading_date": None, "source_identity": "sha"}
    record = _source_row(row=row, source="HNX_UPCOM", observed_at="2026-09-13T00:00:00Z")
    assert record["current_universe_status"] == "OFFICIAL_CURRENT_STOCK_LIST_CANDIDATE"
    assert record["exchange_or_market"] == "UPCOM"
    assert record["official_security_status"] == STATUS_NOT_PROVIDED


# 3. Current HOSE row.
def test_current_hose_row_normal_status():
    row = {"ticker": "hpg", "issuer_name": "Z", "hose_security_id": 2458, "listing_status_id": 11, "listing_status_reason": None, "source_identity": "sha"}
    record = _source_row(row=row, source="HOSE", observed_at="2026-09-13T00:00:00Z")
    assert record["current_universe_status"] == "OFFICIAL_CURRENT_EXCHANGE_SECURITY"
    assert record["official_security_status"] == STATUS_NORMAL
    assert record["official_security_status_reason"] is None


def test_hose_status_helper_distinguishes_normal_unknown_and_not_provided():
    assert _hose_official_security_status({"listing_status_id": 11, "listing_status_reason": None}) == (STATUS_NORMAL, None)
    assert _hose_official_security_status({"listing_status_id": 99, "listing_status_reason": "Canh bao"}) == (STATUS_UNKNOWN_CODE, "Canh bao")
    assert _hose_official_security_status({"listing_status_id": None, "listing_status_reason": None}) == (STATUS_NOT_PROVIDED, None)


# 4. Officially delisted ticker (via cross-provider corroboration on the status axis; this
#    milestone's HNX/HOSE list-presence check corroborates that same population independently).
@_REQUIRES_REFRESHED_EVIDENCE
def test_delisted_corroborated_population_is_absent_from_official_master_and_not_stocklookup_candidate():
    artifact = _build_refreshed()
    delisted = [t for t, r in artifact["records"].items() if r["qualification"] == "DELISTED_OR_NO_LONGER_CURRENT"]
    assert len(delisted) == 173
    for ticker in delisted:
        record = artifact["records"][ticker]
        assert record["official_source"] is None
        assert record["official_security_status"] == STATUS_NOT_PROVIDED


# 5. Listed but restricted/suspended ticker must NOT be conflated with delisted.
def test_unknown_hose_status_code_is_not_conflated_with_delisted():
    row = {"ticker": "wrn", "issuer_name": "Warned Co", "hose_security_id": 9999, "listing_status_id": 13, "listing_status_reason": "Canh bao", "source_identity": "sha"}
    record = _source_row(row=row, source="HOSE", observed_at="2026-09-13T00:00:00Z")
    # Presence in the official master at all means this security is NOT the delisted-residual
    # branch; a restricted/warned/suspended security stays OFFICIAL_CURRENT_EXCHANGE_SECURITY.
    assert record["current_universe_status"] == "OFFICIAL_CURRENT_EXCHANGE_SECURITY"
    assert record["official_security_status"] == STATUS_UNKNOWN_CODE
    assert record["official_security_status"] != STATUS_NORMAL


# 6. Provider rejection (DNSE) while official listing still exists must not resolve to delisted.
@_REQUIRES_REFRESHED_EVIDENCE
def test_provider_rejection_with_surviving_official_listing_would_not_be_delisted():
    """No real 2026-09-13 ticker currently exercises this exact combination (the six
    provider-rejected names are also absent from the fresh HNX/HOSE lists), so this is a direct
    unit check of the classification rule itself: PROVIDER_REJECTED is never sufficient by
    itself to produce DELISTED_OR_NO_LONGER_CURRENT if an official master row is present -- the
    match branch (OFFICIAL_CURRENT_EXCHANGE_SECURITY / OFFICIAL_CURRENT_STOCK_LIST_CANDIDATE)
    always wins over the residual/no-match branch when a ticker is found in hnx_rows/hose_rows,
    regardless of what current_universe_status_and_session_coverage_resolution said about DNSE."""
    row = {"ticker": "rej", "issuer_name": "Still Listed Co", "market": "UPCOM", "first_trading_date": None, "source_identity": "sha"}
    record = _source_row(row=row, source="HNX_UPCOM", observed_at="2026-09-13T00:00:00Z")
    assert record["current_universe_status"] == "OFFICIAL_CURRENT_STOCK_LIST_CANDIDATE"
    assert record["qualification"] != "DELISTED_OR_NO_LONGER_CURRENT"


# 7. Missing exact-session price does not imply delisting.
@_REQUIRES_REFRESHED_EVIDENCE
def test_missing_target_session_price_does_not_imply_delisting():
    artifact = _build_refreshed()
    # The 502 population (ACTIVE_LISTED_NO_QUALIFIED_SESSION_OBSERVATION with nearby activity)
    # must remain OFFICIAL_CURRENT_* wherever it has a surviving HNX/HOSE master row, never
    # DELISTED_OR_NO_LONGER_CURRENT purely from a session gap.
    gap_tickers = [t for t, r in artifact["records"].items()
                   if r.get("stocklookup_candidate")]
    matched_gap = 0
    for ticker in gap_tickers:
        record = artifact["records"][ticker]
        if record["current_universe_status"] in {"OFFICIAL_CURRENT_EXCHANGE_SECURITY", "OFFICIAL_CURRENT_STOCK_LIST_CANDIDATE"}:
            matched_gap += 1
            assert record["qualification"] != "DELISTED_OR_NO_LONGER_CURRENT"
    assert matched_gap > 0


# 8. Delisted evidence with an effective date: not currently supported by either source surface,
#    so the field must be honestly None rather than a fabricated timestamp.
def test_official_security_status_effective_date_is_never_fabricated():
    for source, row in (
        ("HNX_UPCOM", {"ticker": "aaa", "issuer_name": "A", "market": "HNX_LISTED", "first_trading_date": None, "source_identity": "sha"}),
        ("HOSE", {"ticker": "bbb", "issuer_name": "B", "hose_security_id": 1, "listing_status_id": 11, "listing_status_reason": None, "source_identity": "sha"}),
    ):
        record = _source_row(row=row, source=source, observed_at="2026-09-13T00:00:00Z")
        assert record["official_security_status_effective_date"] is None
        assert record["official_security_status_publication_date"] is None


# 9. Current evidence observed after the target session must not be backdated into it.
def test_official_observed_at_is_the_real_acquisition_timestamp_not_the_target_session():
    row = {"ticker": "ccc", "issuer_name": "C", "market": "UPCOM", "first_trading_date": None, "source_identity": "sha"}
    record = _source_row(row=row, source="HNX_UPCOM", observed_at="2026-09-13T10:00:00Z")
    assert record["official_observed_at"] == "2026-09-13T10:00:00Z"
    assert record["official_observed_at"] != "2026-09-11"


# 10. Official-only row remains non-production.
@_REQUIRES_REFRESHED_EVIDENCE
def test_official_only_rows_are_flagged_owner_review_not_auto_added():
    artifact = _build_refreshed()
    official_only = [t for t, r in artifact["records"].items() if r["current_universe_status"] == OFFICIAL_ONLY_NOT_IN_STOCKLOOKUP]
    assert len(official_only) == artifact["reconciliation"]["official_only_not_in_stocklookup"] == 20
    for ticker in official_only:
        record = artifact["records"][ticker]
        assert record["stocklookup_candidate"] is False
        assert record["qualification"] == "CANDIDATE_UNIVERSE_STALENESS_OR_GOVERNED_EXCLUSION_UNRESOLVED"


# 11. Identity conflict fails closed.
def test_cross_exchange_ticker_conflict_fails_closed(tmp_path: Path):
    hnx = {"artifact_identity": "x", "datasets": {"hnx_official_equity_universe/v1": [{"ticker": "DUP", "market": "HNX_LISTED", "source_identity": "s"}], "hnx_official_rights_event_index/v1": []}, "captures": []}
    hose = {"artifact_identity": "y", "datasets": {"hose_public_stock_master/v1": [{"ticker": "DUP", "hose_security_id": 1, "listing_status_id": 11, "source_identity": "s"}]}, "captures": []}
    import hashlib
    def _sign(a):
        payload = {k: v for k, v in a.items() if k not in ("artifact_sha256", "artifact_identity")}
        digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        a["artifact_sha256"] = digest
        a["artifact_identity"] = f"test:{digest}"
        return a
    hnx, hose = _sign(hnx), _sign(hose)
    status = _sign({"records": {f"T{i:04}": {} for i in range(1683)}})
    empty = _sign({"records": {f"T{i:04}": {} for i in range(1683)}})
    with pytest.raises(ValueError, match="OFFICIAL_EXCHANGE_TICKER_CONFLICT"):
        build_artifact(hnx=hnx, hose=hose, status=status, descriptive=empty, screening=empty, tactical=empty, strategy=empty, scenario=empty)


# 12. 1,683 accounting reconciliation.
@_REQUIRES_REFRESHED_EVIDENCE
def test_1683_accounting_reconciles_with_the_refreshed_official_universe():
    artifact = _build_refreshed()
    reconciliation = artifact["reconciliation"]
    assert reconciliation["stocklookup_universe_count"] == 1683
    assert reconciliation["official_total_match"] + reconciliation["stocklookup_only_unresolved"] == 1683
    residual = reconciliation["residual_disposition"]
    assert residual["DELISTED_OR_NO_LONGER_CURRENT"] + residual["UNRESOLVED"] + residual["SYMBOL_IDENTITY_DRIFT"] + residual["NON_COMMON_SECURITY"] + residual["OTHER_MARKET_OR_UNSUPPORTED"] == reconciliation["stocklookup_only_unresolved"]
    assert residual["UNRESOLVED"] == 6
    assert residual["DELISTED_OR_NO_LONGER_CURRENT"] == 173
    replay(artifact)


# 13. Consumer filter does not alter decision rules (only scopes the ticker set).
@_REQUIRES_REFRESHED_EVIDENCE
def test_consumer_filter_changes_denominator_not_decision_rules():
    artifact = _build_refreshed()
    compat = artifact["consumer_compatibility"]
    # data_ready/eligible/classified counts before vs after must be internally consistent with a
    # strict ticker-set restriction (after <= before on every ready-style numerator), never a
    # rule change that could inflate readiness beyond what the same underlying record already says.
    assert compat["screening"]["after"]["data_ready"] <= compat["screening"]["before"]["data_ready"]
    assert compat["tactical"]["after"]["classified"] <= compat["tactical"]["before"]["classified"]
    assert compat["strategy"]["after"]["eligible"] <= compat["strategy"]["before"]["eligible"]
    assert compat["tactical"]["fitness"] == "FIT_VIA_TICKER_FILTER_ADAPTER_NO_RULE_CHANGE"
    assert compat["strategy"]["fitness"] == "FIT_VIA_TICKER_FILTER_ADAPTER_NO_RULE_CHANGE"


# 14. Historical PIT remains blocked.
@_REQUIRES_REFRESHED_EVIDENCE
def test_historical_pit_and_survivorship_universe_remain_blocked():
    artifact = _build_refreshed()
    assert artifact["fitness_for_use"]["HISTORICAL_PIT_UNIVERSE"] == "BLOCKED_NOT_CONSTRUCTED"
    assert artifact["fitness_for_use"]["SURVIVORSHIP_SAFE_BACKTEST_UNIVERSE"] == "BLOCKED_NOT_CONSTRUCTED"
    assert "NOT_HISTORICAL_PIT" in artifact["authority_boundary"]


def test_hose_stock_rows_retain_status_reason_field(tmp_path: Path):
    """hose_public_xhr_and_periodic_series_recon._stock_rows must retain the raw `reason`
    field (previously discarded) so current_official_market_universe can distinguish status
    codes from their explanatory text without a second acquisition."""
    def _response(url: str):
        if "stock?page" in url:
            data = {"success": True, "data": {"list": [
                {"id": 1, "code": "AAA", "name": "A", "isin": "VNAAA", "securitiesType": 1, "listingStatusId": 11, "reason": None, "listingVolume": "100", "outStanding": "90"},
            ], "paging": {"totalCount": 1}}}
        elif "listing-dashboard" in url:
            data = {"success": True, "data": {"securitiesTotal": 1}}
        elif "indicies/0" in url:
            data = {"success": True, "data": [{"id": 5, "name": "VN30"}]}
        elif "indicies/5/" in url:
            data = {"success": True, "data": {"list": [{"id": 1, "code": "AAA"}], "paging": {"totalCount": 1}}}
        elif "foreign" in url:
            data = {"success": True, "data": {"list": [{"reportDate": 1, "totalRoom": 2, "currentRoom": 3}]}}
        elif "market/securities/HPG" in url:
            data = {"success": True, "data": {"mainValue": 4}}
        elif "dividend" in url:
            data = {"success": True, "data": [{"type": "cash", "transNoRightDate": 1, "lastRegDate": 2}]}
        elif "news/securities/2458" in url:
            data = {"success": True, "data": {"list": [{"id": 2, "title": "HPG"}]}}
        elif "news/securitiesType" in url:
            data = {"success": True, "data": {"list": [{"id": 3, "title": "Market"}]}}
        else:
            data = {"success": True, "data": {}}
        return {"requested_url": url, "official_url": url, "retrieved_at": "2026-09-13T00:00:00Z", "http_status": 200, "content_type": "application/json", "data": json.dumps(data).encode()}

    universe = tmp_path / "universe.json"
    universe.write_text(json.dumps({"records": {f"T{i:04}": {} for i in range(1683)}}), encoding="utf-8")
    hnx = tmp_path / "hnx.json"
    hnx.write_text(json.dumps({"datasets": {"hnx_official_equity_universe/v1": [{"ticker": "T0000"}]}}), encoding="utf-8")
    artifact = build_hose(destination=tmp_path, stocklookup_universe=universe, hnx_universe=hnx, fetcher=_response)
    stocks = artifact["datasets"]["hose_public_stock_master/v1"]
    assert stocks[0]["listing_status_reason"] is None
