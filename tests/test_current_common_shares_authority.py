from __future__ import annotations

import json
from pathlib import Path

from current_common_shares_authority import (
    COMMON_OUTSTANDING,
    CORPORATE_ACTION_RECONCILIATION_REQUIRED,
    PROVIDER_REPORTED_CURRENT_RESEARCH,
    PROVIDER_REPORTED_LAGGED,
    QUALIFIED_CURRENT_COMMON_SHARES,
    QUALIFIED_OFFICIAL_ANCHOR_NOT_CURRENT,
    UNVERIFIABLE_FRESHNESS,
    build_current_common_shares_authority,
    coverage_includes_session,
    derive_common_shares_from_components,
    reconcile_subsequent_events,
    resolve_ticker_share_authority,
)
from current_share_authority import SHARE_IDENTITIES
from market_wide_current_valuation_input_scaleout import build_current_valuation_artifact
from tools.derive_market_wide_current_valuation_input_scaleout import FROZEN_OUTPUTS, _refuse_frozen_output

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "daily_research_session_input_registry.json"
FROZEN_20260821 = "market_wide_current_valuation:e6d015f2feee4cc5c5969d7a1fddac9d2f1b2b55918adb4ea199920e4455b29a"
FROZEN_20260824 = "market_wide_current_valuation:b9ca122464fa5e70c127bae642a32ac4dacc786f1682a828445c5754f4110388"
SESSION = "2026-08-21"


def _official_universe(*tickers: str) -> dict:
    return {
        "artifact_identity": "official:test",
        "records": {
            ticker: {"stocklookup_candidate": True, "current_universe_status": "OFFICIAL_CURRENT_EXCHANGE_SECURITY"}
            for ticker in tickers
        },
    }


def _hpg_common(**overrides) -> dict:
    row = {
        "identity": COMMON_OUTSTANDING,
        "value": 8_442_964_520,
        "effective_date": "2026-07-02",
        "coverage_through": "2026-07-30",
        "qualification_state": "QUALIFIED",
        "citation_id": "984a47fe87286adfd2f0ac46cb8b3649fe3c6ad3f5d21a14634fda76b861ac8e",
        "source": "official_corporate_action_result",
    }
    row.update(overrides)
    return row


def test_identities_do_not_collapse_and_weighted_average_never_qualifies_current():
    assert "issued_shares" in SHARE_IDENTITIES
    assert "period_end_shares" in SHARE_IDENTITIES
    assert "weighted_average_basic_shares" in SHARE_IDENTITIES
    wa = resolve_ticker_share_authority(
        "VNM", session=SESSION,
        official_period_end={"identity": "period_end_shares", "value": 2_089_955_445, "effective_on": "2024-12-31"},
        weighted_average={"identity": "weighted_average_basic_shares", "value": 2_089_955_445},
        resolver_row={"authority": "unavailable"},
    )
    assert wa["authority_tier"] != QUALIFIED_CURRENT_COMMON_SHARES
    assert wa["canonical_share_identity"] == "period_end_shares"
    assert "WEIGHTED_AVERAGE_SHARES_ARE_NOT_CURRENT_COMMON_SHARES" in wa["warnings"]
    assert derive_common_shares_from_components(None, None)["value"] is None
    assert derive_common_shares_from_components(100, None)["reason"] == "ISSUED_MINUS_TREASURY_REQUIRES_BOTH_EXPLICIT_COMPONENTS"


def test_official_anchor_without_session_coverage_is_not_current():
    hpg = resolve_ticker_share_authority("HPG", session=SESSION, official_common=_hpg_common())
    assert hpg["authority_tier"] == QUALIFIED_OFFICIAL_ANCHOR_NOT_CURRENT
    assert hpg["coverage_through_session"] is False
    assert hpg["value"] == 8_442_964_520
    assert hpg["fitness_for_use"] == "RESEARCH_USABLE_NOT_AUTHORITATIVE"
    assert coverage_includes_session("2026-07-02", "2026-07-30", SESSION) is False
    current = resolve_ticker_share_authority("HPG", session="2026-07-30", official_common=_hpg_common())
    assert current["authority_tier"] == QUALIFIED_CURRENT_COMMON_SHARES
    assert current["coverage_through_session"] is True


def test_planned_event_does_not_terminate_and_executed_without_resulting_shares_does():
    lagged = {
        "authority": "provider_reported_lagged", "value": 100, "share_concept": "ISSUED_SHARES",
        "observation_date": "2026-08-14", "observation_lag_days": 7,
        "reason": "observation predates the session",
    }
    planned = resolve_ticker_share_authority(
        "AAA", session=SESSION, resolver_row=lagged,
        official_events=[{"event_type": "RIGHTS", "event_state": "UPCOMING", "ex_date": "2026-09-04", "execution_date": None}],
    )
    assert planned["authority_tier"] == PROVIDER_REPORTED_LAGGED
    assert planned["value"] == 100
    interrupted = resolve_ticker_share_authority(
        "BBB", session=SESSION, resolver_row=lagged,
        official_events=[{
            "event_type": "STOCK_DIVIDEND", "event_state": "RECENT",
            "execution_date": "2026-08-18", "resulting_shares": None,
        }],
    )
    assert interrupted["authority_tier"] == CORPORATE_ACTION_RECONCILIATION_REQUIRED
    assert interrupted["value"] is None
    inferred = reconcile_subsequent_events(
        [{"event_type": "BONUS", "ex_date": "2026-08-18", "execution_date": None}],
        after_date="2026-08-14", session=SESSION,
    )
    assert "CORPORATE_ACTION_TIMING_UNRESOLVED_NO_EX_DATE_INFERRED" in inferred["blockers"]


def test_stale_unverifiable_and_provider_current_research_fail_closed_or_labelled():
    ssi = resolve_ticker_share_authority(
        "SSI", session=SESSION,
        resolver_row={
            "authority": "provider_reported_unverifiable_freshness",
            "undated_share_relevant_events": ["ISS"],
            "reason": "missing_explicit_official_ex_date_on_share_relevant_event",
            "observation_date": "2026-08-14",
        },
    )
    assert ssi["authority_tier"] == UNVERIFIABLE_FRESHNESS
    assert ssi["value"] is None
    current = resolve_ticker_share_authority(
        "FPT", session=SESSION,
        resolver_row={"authority": "provider_reported_current", "value": 50, "observation_date": "2026-08-21", "share_concept": "ISSUED_SHARES"},
    )
    assert current["authority_tier"] == PROVIDER_REPORTED_CURRENT_RESEARCH
    assert current["canonical_share_identity"] == "ISSUED_SHARES"
    assert current["fitness_for_use"] == "RESEARCH_USABLE_NOT_AUTHORITATIVE"


def test_market_wide_denominator_and_one_terminal_per_ticker():
    resolution = {"tickers": {
        "HPG": {"authority": "qualified_official", "value": 8_442_964_520, "official_anchor_effective_date": "2026-07-02", "share_concept": "current_common_shares_outstanding"},
        "AAA": {"authority": "provider_reported_lagged", "value": 10, "observation_date": "2026-08-14", "share_concept": "ISSUED_SHARES"},
        "SSI": {"authority": "provider_reported_unverifiable_freshness", "undated_share_relevant_events": ["ISS"], "observation_date": "2026-08-14"},
        "VCB": {"authority": "provider_reported_unverifiable_freshness", "undated_share_relevant_events": ["ISS"], "observation_date": "2026-08-14"},
        "FPT": {"authority": "provider_reported_current", "value": 20, "observation_date": "2026-08-21", "share_concept": "ISSUED_SHARES"},
    }}
    artifact = build_current_common_shares_authority(
        session=SESSION, official_universe=_official_universe("HPG", "AAA", "SSI", "VCB", "FPT"),
        share_resolution=resolution, official_common_anchors={"HPG": _hpg_common()},
    )
    assert artifact["coverage"]["universe_denominator"] == 5
    assert artifact["coverage"]["denominator_reconciles"] is True
    assert artifact["coverage"]["unexplained_count"] == 0
    assert len(artifact["records"]) == 5
    assert {row["authority_tier"] for row in artifact["records"].values()} <= {
        QUALIFIED_CURRENT_COMMON_SHARES, QUALIFIED_OFFICIAL_ANCHOR_NOT_CURRENT,
        PROVIDER_REPORTED_CURRENT_RESEARCH, PROVIDER_REPORTED_LAGGED,
        UNVERIFIABLE_FRESHNESS, CORPORATE_ACTION_RECONCILIATION_REQUIRED,
    }
    assert artifact["records"]["HPG"]["authority_tier"] == QUALIFIED_OFFICIAL_ANCHOR_NOT_CURRENT
    replay = build_current_common_shares_authority(
        session=SESSION, official_universe=_official_universe("HPG", "AAA", "SSI", "VCB", "FPT"),
        share_resolution=resolution, official_common_anchors={"HPG": _hpg_common()},
    )
    assert replay["artifact_identity"] == artifact["artifact_identity"]


def test_existing_valuation_engine_consumes_share_authority_without_formula_changes():
    prices = {"resolved_completed_session": SESSION, "source": "DNSE", "snapshot_identity": "price:1", "records": {
        "HPG": {"disposition": "EXACT_SESSION_RETAINED", "observations": [{"session": SESSION, "close": 21_700}]},
        "AAA": {"disposition": "EXACT_SESSION_RETAINED", "observations": [{"session": SESSION, "close": 10_000}]},
        "SSI": {"disposition": "EXACT_SESSION_RETAINED", "observations": [{"session": SESSION, "close": 20_000}]},
    }}
    fundamentals = {"artifact_identity": "fund:1", "records": {
        "HPG": {"entity_class": "corporate", "authority_tier": "OFFICIAL_QUALIFIED", "metrics": [{"metric_id": "net_income"}]},
        "AAA": {"entity_class": "corporate", "authority_tier": "OFFICIAL_QUALIFIED", "metrics": [{"metric_id": "revenue"}]},
        "SSI": {"entity_class": "securities", "authority_tier": "OFFICIAL_QUALIFIED", "metrics": [{"metric_id": "profit_after_tax_parent"}]},
    }}
    shares = {"artifact_identity": "shares:1", "projected_coverage_impact": {"cohort_rows": []}}
    p3e = {"artifact_identity": "p3e:1", "refreshed_panel_data": {"issuers": [
        {"issuer_identity": {"ticker": "HPG", "entity_type": "corporate"}, "facts": [
            {"canonical_metric": "net_income", "value": 10, "qualification_state": "QUALIFIED", "reporting_period": "2025", "observed_at": "2026-01-01"},
            {"canonical_metric": "shareholders_equity", "value": 100, "qualification_state": "QUALIFIED", "reporting_period": "2025", "observed_at": "2026-01-01"},
            {"canonical_metric": "revenue", "value": 200, "qualification_state": "QUALIFIED", "reporting_period": "2025", "observed_at": "2026-01-01"},
            {"canonical_metric": "cash_and_equivalents", "value": 20, "qualification_state": "QUALIFIED", "reporting_period": "2025", "observed_at": "2026-01-01"},
            {"canonical_metric": "total_interest_bearing_debt", "value": 50, "qualification_state": "QUALIFIED", "reporting_period": "2025", "observed_at": "2026-01-01"},
        ]},
        {"issuer_identity": {"ticker": "AAA", "entity_type": "corporate"}, "facts": [
            {"canonical_metric": "net_income", "value": 10, "qualification_state": "QUALIFIED", "reporting_period": "2025", "observed_at": "2026-01-01"},
            {"canonical_metric": "shareholders_equity", "value": 100, "qualification_state": "QUALIFIED", "reporting_period": "2025", "observed_at": "2026-01-01"},
            {"canonical_metric": "revenue", "value": 200, "qualification_state": "QUALIFIED", "reporting_period": "2025", "observed_at": "2026-01-01"},
            {"canonical_metric": "cash_and_equivalents", "value": 20, "qualification_state": "QUALIFIED", "reporting_period": "2025", "observed_at": "2026-01-01"},
            {"canonical_metric": "total_interest_bearing_debt", "value": 50, "qualification_state": "QUALIFIED", "reporting_period": "2025", "observed_at": "2026-01-01"},
        ]},
    ]}}
    authority = build_current_common_shares_authority(
        session=SESSION, official_universe=_official_universe("HPG", "AAA", "SSI"),
        share_resolution={"tickers": {
            "HPG": {"authority": "qualified_official", "value": 8_442_964_520, "official_anchor_effective_date": "2026-07-02"},
            "AAA": {"authority": "provider_reported_lagged", "value": 100, "observation_date": "2026-08-14", "share_concept": "ISSUED_SHARES"},
            "SSI": {"authority": "provider_reported_unverifiable_freshness", "undated_share_relevant_events": ["ISS"]},
        }},
        official_common_anchors={"HPG": _hpg_common()},
    )
    before = build_current_valuation_artifact(
        price_snapshot=prices, fundamental_artifact=fundamentals, share_promotion_artifact=shares, p3e_artifact=p3e,
        official_universe=_official_universe("HPG", "AAA", "SSI"),
        share_resolution={"tickers": {
            "HPG": {"authority": "qualified_official", "value": 8_442_964_520, "share_concept": "current_common_shares_outstanding"},
            "AAA": {"authority": "provider_reported_lagged", "value": 100, "share_concept": "ISSUED_SHARES"},
            "SSI": {"authority": "provider_reported_unverifiable_freshness", "value": None},
        }},
    )
    after = build_current_valuation_artifact(
        price_snapshot=prices, fundamental_artifact=fundamentals, share_promotion_artifact=shares, p3e_artifact=p3e,
        official_universe=_official_universe("HPG", "AAA", "SSI"),
        share_authority_artifact=authority,
    )
    assert after["records"]["HPG"]["share_basis_input"]["status"] == QUALIFIED_OFFICIAL_ANCHOR_NOT_CURRENT
    assert after["records"]["HPG"]["metrics"]["market_cap"]["status"] == "RESEARCH_USABLE"
    assert after["records"]["HPG"]["metrics"]["market_cap"]["status"] != "READY"
    assert after["records"]["AAA"]["metrics"]["market_cap"]["status"] == "RESEARCH_USABLE"
    assert after["records"]["SSI"]["metrics"]["market_cap"]["status"] == "BLOCKED"
    assert after["coverage"]["share_ready"] == 0
    assert after["value_strategy_readiness"]["eligible"] == 0
    assert before["coverage"]["share_ready"] == 0
    current = build_current_valuation_artifact(
        price_snapshot=prices, fundamental_artifact=fundamentals, share_promotion_artifact=shares, p3e_artifact=p3e,
        official_universe=_official_universe("HPG", "AAA", "SSI"),
        share_authority_artifact=build_current_common_shares_authority(
            session="2026-07-30", official_universe=_official_universe("HPG", "AAA", "SSI"),
            share_resolution={"tickers": {
                "HPG": {"authority": "qualified_official", "value": 8_442_964_520},
                "AAA": {"authority": "provider_reported_lagged", "value": 100, "observation_date": "2026-08-14", "share_concept": "ISSUED_SHARES"},
                "SSI": {"authority": "provider_reported_unverifiable_freshness"},
            }},
            official_common_anchors={"HPG": _hpg_common()},
        ),
    )
    assert current["records"]["HPG"]["metrics"]["market_cap"]["status"] == "READY"
    assert current["records"]["HPG"]["metrics"]["market_cap"]["formula"] == "current_session_close * share_basis_value"
    assert current["coverage"]["share_ready"] == 1


def test_materialized_scaleout_report_reconciles_when_present():
    path = ROOT / "operations-review" / "current-common-shares-authority-and-scaleout-v1" / "current_common_shares_authority_scaleout_report.json"
    if not path.is_file():
        return
    report = json.loads(path.read_text(encoding="utf-8"))
    dist = report["authority_tier_distribution"]
    assert report["universe_denominator"] == 1507
    assert report["denominator_reconciles"] is True
    assert report["unexplained_count"] == 0
    assert sum(dist.values()) == 1507
    assert dist.get("QUALIFIED_CURRENT_COMMON_SHARES", 0) == 0
    assert dist.get("QUALIFIED_OFFICIAL_ANCHOR_NOT_CURRENT") == 1
    assert dist.get("UNVERIFIABLE_FRESHNESS") == 2
    assert report["value_eligibility_after"] == 0
    assert report["valuation_unlock"]["market_cap"]["READY_after"] == 0
    assert FROZEN_20260821 in report["frozen_identities_unchanged"]
    assert FROZEN_20260824 in report["frozen_identities_unchanged"]


def test_frozen_session_identities_and_output_refuse_path_unchanged():
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert registry["sessions"]["2026-08-21"]["valuation"]["artifact_identity"] == FROZEN_20260821
    assert registry["sessions"]["2026-08-24"]["valuation"]["artifact_identity"] == FROZEN_20260824
    try:
        _refuse_frozen_output(next(iter(FROZEN_OUTPUTS)))
        raise AssertionError("frozen output must be refused")
    except ValueError as exc:
        assert "REFUSING_TO_OVERWRITE_FROZEN_VALUATION_ARTIFACT" in str(exc)
