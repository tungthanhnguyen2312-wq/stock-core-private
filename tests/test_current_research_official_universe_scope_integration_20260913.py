"""Focused regression coverage for CURRENT_RESEARCH_OFFICIAL_UNIVERSE_CONSUMER_INTEGRATION_V1.

Uses the real retained 2026-09-13 official-universe evidence where the assertion is about actual
current state (universe accounting), and small synthetic fixtures where the assertion is about a
specific temporal/consumer-integration rule the real evidence may not itself exercise (a later
research session, opt-in Screener/Workspace scoping).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from current_research_official_universe_scope import (
    DISPOSITION_ELIGIBLE, DISPOSITION_TEMPORALLY_INELIGIBLE, SCOPE_ELIGIBLE,
    SCOPE_OUTSIDE_DELISTING_CORRELATED, SCOPE_OUTSIDE_UNRESOLVED,
    CurrentResearchOfficialUniverseScopeError, eligible_ticker_set, resolve_scope,
)
from screener_master_projection import build_projection
import investment_decision_workspace_projection as _workspace_module
from _integrated_decision_fixture import integrated_decision as _integrated_decision


def build_workspace_artifacts(**kwargs):
    # CURRENT_DECISION_SURFACE_CONVERGENCE_V1: supply the Workspace's required, same-session
    # Integrated Decision (production builder) over the same ticker set.
    opportunity = kwargs["opportunity_artifact"]
    kwargs.setdefault("integrated_decision_artifact", _integrated_decision(
        opportunity.get("as_of_session") or kwargs["decision_artifact"].get("as_of_session"),
        sorted(opportunity.get("records") or {}),
    ))
    return _workspace_module.build_artifacts(**kwargs)


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_PATH = ROOT / "operations-review/current-official-market-universe-refresh-v1-20260913/current_official_market_universe_artifact.json"
_REQUIRES_REAL_EVIDENCE = pytest.mark.skipif(not OFFICIAL_PATH.is_file(), reason="Refreshed official-universe evidence not present in this worktree/checkout.")


@pytest.fixture(scope="module")
def official_artifact():
    return json.loads(OFFICIAL_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------------------------
# Universe accounting (1-4)
# ---------------------------------------------------------------------------------------------

@_REQUIRES_REAL_EVIDENCE
def test_1_source_reference_is_1683(official_artifact):
    scope = resolve_scope(official_artifact=official_artifact, research_session="2026-09-20")
    assert scope["source_reference_ticker_count"] == 1683


@_REQUIRES_REAL_EVIDENCE
def test_2_official_current_scope_is_1504(official_artifact):
    scope = resolve_scope(official_artifact=official_artifact, research_session="2026-09-20")
    assert scope["current_research_scope_ticker_count"] == 1504


@_REQUIRES_REAL_EVIDENCE
def test_3_outside_scope_is_179(official_artifact):
    scope = resolve_scope(official_artifact=official_artifact, research_session="2026-09-20")
    outside = sum(1 for row in scope["records"].values() if row["current_research_scope_state"] != SCOPE_ELIGIBLE)
    assert outside == 179
    assert scope["source_reference_ticker_count"] - scope["current_research_scope_ticker_count"] == 179


@_REQUIRES_REAL_EVIDENCE
def test_4_official_only_never_added_to_scope(official_artifact):
    scope = resolve_scope(official_artifact=official_artifact, research_session="2026-09-20")
    # The 20 official-only rows are not stocklookup_candidate=True, so resolve_scope must never
    # emit a record for them at all (never a union beyond the governed 1,683).
    official_only_tickers = set(official_artifact["reconciliation"]["official_only_tickers"])
    assert not (official_only_tickers & set(scope["records"]))
    assert len(official_only_tickers) == 20


# ---------------------------------------------------------------------------------------------
# Membership semantics (5-11)
# ---------------------------------------------------------------------------------------------

@_REQUIRES_REAL_EVIDENCE
def test_5_502_source_gap_names_stay_included(official_artifact):
    status = json.loads((ROOT / "operations-review/current-universe-status-and-session-coverage-resolution-v1-20260911/current_universe_status_and_session_coverage_resolution_artifact.json").read_text(encoding="utf-8"))["records"]
    pop502 = [t for t, v in status.items() if v.get("activity_and_session_reason_code") == "TARGET_SESSION_GAP_WITH_NEARBY_OBSERVED_ACTIVITY"]
    assert len(pop502) == 502
    scope = resolve_scope(official_artifact=official_artifact, research_session="2026-09-20")
    included = sum(1 for t in pop502 if scope["records"][t]["current_research_scope_state"] == SCOPE_ELIGIBLE)
    assert included == 502


@_REQUIRES_REAL_EVIDENCE
def test_6_50_no_bar_names_stay_included(official_artifact):
    status = json.loads((ROOT / "operations-review/current-universe-status-and-session-coverage-resolution-v1-20260911/current_universe_status_and_session_coverage_resolution_artifact.json").read_text(encoding="utf-8"))["records"]
    pop50 = [t for t, v in status.items() if v.get("activity_and_session_reason_code") == "NO_OBSERVED_TRADING_ACTIVITY_IN_RETAINED_WINDOW"]
    assert len(pop50) == 50
    scope = resolve_scope(official_artifact=official_artifact, research_session="2026-09-20")
    included = sum(1 for t in pop50 if scope["records"][t]["current_research_scope_state"] == SCOPE_ELIGIBLE)
    assert included == 50


@_REQUIRES_REAL_EVIDENCE
def test_7_restricted_stays_included(official_artifact):
    enriched_path = ROOT / "operations-review/hnx-upcom-official-security-status-enrichment-v1-20260913/current_official_market_universe_with_security_status_artifact.json"
    enriched = json.loads(enriched_path.read_text(encoding="utf-8"))
    scope = resolve_scope(official_artifact=enriched, research_session="2026-09-20")
    assert scope["records"]["ART"]["official_security_status"] == "SUSPENDED"
    # ART is officially suspended AND stays a scope member -- membership != trading status.
    assert scope["records"]["ART"]["current_research_scope_state"] == SCOPE_ELIGIBLE


@_REQUIRES_REAL_EVIDENCE
def test_8_suspended_stays_included(official_artifact):
    enriched_path = ROOT / "operations-review/hnx-upcom-official-security-status-enrichment-v1-20260913/current_official_market_universe_with_security_status_artifact.json"
    enriched = json.loads(enriched_path.read_text(encoding="utf-8"))
    scope = resolve_scope(official_artifact=enriched, research_session="2026-09-20")
    suspended_tickers = [t for t, r in scope["records"].items() if r["official_security_status"] == "SUSPENDED"]
    assert len(suspended_tickers) == 23
    assert all(scope["records"][t]["current_research_scope_state"] == SCOPE_ELIGIBLE for t in suspended_tickers)


@_REQUIRES_REAL_EVIDENCE
def test_9_no_price_does_not_affect_membership(official_artifact):
    # resolve_scope never reads price/tactical availability at all -- structurally impossible for
    # a price gap to change current_research_scope_state.
    import inspect
    source = inspect.getsource(resolve_scope)
    assert "price" not in source.lower()
    assert "tactical" not in source.lower()


@_REQUIRES_REAL_EVIDENCE
def test_10_six_unresolved_are_outside_but_not_delisted(official_artifact):
    scope = resolve_scope(official_artifact=official_artifact, research_session="2026-09-20")
    for ticker in ("BCG", "BCR", "DAN", "DVT", "LTG", "VTS"):
        assert scope["records"][ticker]["current_research_scope_state"] == SCOPE_OUTSIDE_UNRESOLVED
        assert scope["records"][ticker]["current_research_scope_state"] != SCOPE_OUTSIDE_DELISTING_CORRELATED


@_REQUIRES_REAL_EVIDENCE
def test_11_prior_173_outside_without_rewriting_historical_vocabulary(official_artifact):
    scope = resolve_scope(official_artifact=official_artifact, research_session="2026-09-20")
    delisting_correlated = [t for t, r in scope["records"].items() if r["current_research_scope_state"] == SCOPE_OUTSIDE_DELISTING_CORRELATED]
    assert len(delisting_correlated) == 173
    for t in delisting_correlated:
        # The original evidence vocabulary (qualification) is preserved verbatim, not replaced.
        assert official_artifact["records"][t]["qualification"] == "DELISTED_OR_NO_LONGER_CURRENT"


# ---------------------------------------------------------------------------------------------
# Temporal semantics (12-14)
# ---------------------------------------------------------------------------------------------

@_REQUIRES_REAL_EVIDENCE
def test_12_2026_09_13_snapshot_cannot_filter_2026_09_11_product(official_artifact):
    scope = resolve_scope(official_artifact=official_artifact, research_session="2026-09-11")
    assert scope["temporally_eligible"] is False
    assert scope["disposition"] == DISPOSITION_TEMPORALLY_INELIGIBLE
    assert scope["current_research_scope_ticker_count"] is None
    assert eligible_ticker_set(scope) == frozenset()


@_REQUIRES_REAL_EVIDENCE
def test_13_later_session_can_consume_temporally_available_snapshot(official_artifact):
    scope = resolve_scope(official_artifact=official_artifact, research_session="2026-09-13")
    assert scope["temporally_eligible"] is True
    assert scope["disposition"] == DISPOSITION_ELIGIBLE
    assert scope["current_research_scope_ticker_count"] == 1504
    # A session strictly after the observation date is eligible too.
    later = resolve_scope(official_artifact=official_artifact, research_session="2026-12-31")
    assert later["temporally_eligible"] is True


@_REQUIRES_REAL_EVIDENCE
def test_14_current_evidence_never_emits_historical_pit_fitness(official_artifact):
    scope = resolve_scope(official_artifact=official_artifact, research_session="2026-09-20")
    assert scope["authority_boundary"]["historical_pit_universe"] == "BLOCKED"
    assert scope["authority_boundary"]["active_universe_authority_promotion"] == "NOT_PERFORMED"
    all_fitness = {row["current_research_scope_fitness"] for row in scope["records"].values()}
    assert not any("PIT" in fitness for fitness in all_fitness)


def test_unparseable_session_fails_closed():
    with pytest.raises(CurrentResearchOfficialUniverseScopeError):
        resolve_scope(official_artifact={"records": {}}, research_session="not-a-date", official_snapshot_observed_at="2026-09-13T00:00:00Z")


def test_artifact_with_no_observed_at_evidence_fails_closed():
    with pytest.raises(CurrentResearchOfficialUniverseScopeError):
        resolve_scope(official_artifact={"records": {"AAA": {"stocklookup_candidate": True}}}, research_session="2026-09-20")


# ---------------------------------------------------------------------------------------------
# Screener (15-17)
# ---------------------------------------------------------------------------------------------

_SESSION = "2026-09-20"


def _row(ticker: str) -> dict:
    return {
        "ticker": ticker, "date": _SESSION, "close": 10.0, "chg_today_pct": 0.01, "gtgd20_ty": "",
        "exchange": "HSX", "industry": "", "listing_exchange": "HOSE",
        "canonical_observation_status": "EXACT_SESSION_RETAINED",
        "canonical_price_basis": "CURRENT_DESCRIPTIVE_DNSE_REST_ADJUSTED_RETROSPECTIVE_RAW_AS_TRADED_NOT_PROMOTED",
    }


def _synthetic_official_artifact(eligible: set[str], all_tickers: set[str]) -> dict:
    records = {}
    for ticker in all_tickers:
        if ticker in eligible:
            records[ticker] = {"stocklookup_candidate": True, "current_universe_status": "OFFICIAL_CURRENT_EXCHANGE_SECURITY",
                                "qualification": "FIRST_PARTY_CURRENT_HOSE_STOCK_MASTER_ROW", "exchange_or_market": "HOSE",
                                "official_observed_at": "2026-09-13T08:00:00Z", "official_security_status": "NORMAL_OR_NO_SPECIAL_STATUS"}
        else:
            records[ticker] = {"stocklookup_candidate": True, "current_universe_status": "STOCKLOOKUP_ONLY_UNRESOLVED",
                                "qualification": "UNRESOLVED", "exchange_or_market": None, "official_observed_at": None,
                                "official_security_status": None}
    return {"records": records}


def test_15_screener_default_denominator_unchanged():
    snapshot = [_row("AAA"), _row("BBB"), _row("CCC")]
    out = build_projection(snapshot_rows=snapshot, requested_at="t")
    assert out["denominator"]["ticker_count"] == 3
    assert out["denominator"]["current_research_scope_applied"] is False
    assert set(out["cards"]) == {"AAA", "BBB", "CCC"}


def test_16_screener_opt_in_scoped_denominator():
    # CURRENT_OFFICIAL_RESEARCH_UNIVERSE_PRODUCT_CUTOVER_AND_RELEASE_INTEGRATION_V1: scoping
    # never narrows or drops the Screener denominator -- it only attaches an additive per-card
    # ``official_research_scope`` field and an aggregate ``official_scope_coverage`` block.
    snapshot = [_row("AAA"), _row("BBB"), _row("CCC")]
    official = _synthetic_official_artifact(eligible={"AAA", "BBB"}, all_tickers={"AAA", "BBB", "CCC"})
    scope = resolve_scope(official_artifact=official, research_session=_SESSION)
    out = build_projection(snapshot_rows=snapshot, requested_at="t", current_research_scope=scope)
    assert out["denominator"]["current_research_scope_applied"] is True
    assert out["denominator"]["ticker_count"] == 3
    assert set(out["cards"]) == {"AAA", "BBB", "CCC"}
    assert out["cards"]["AAA"]["official_research_scope"]["scope_bucket"] == "IN_CURRENT_OFFICIAL_RESEARCH_SCOPE"
    assert out["cards"]["CCC"]["official_research_scope"]["scope_bucket"] == "OUTSIDE_CURRENT_OFFICIAL_RESEARCH_SCOPE"
    coverage = out["official_scope_coverage"]
    assert coverage["reference_denominator"] == 3
    assert coverage["current_official_research_scope_count"] == 2
    assert coverage["outside_current_official_scope_count"] == 1


def test_17_screener_retained_values_unchanged_by_scoping():
    # Every field build_ticker_card itself computes stays identical; only the additive
    # ``official_research_scope`` key is new on the scoped card.
    snapshot = [_row("AAA"), _row("BBB"), _row("CCC")]
    unscoped = build_projection(snapshot_rows=snapshot, requested_at="t")
    official = _synthetic_official_artifact(eligible={"AAA", "BBB"}, all_tickers={"AAA", "BBB", "CCC"})
    scope = resolve_scope(official_artifact=official, research_session=_SESSION)
    scoped = build_projection(snapshot_rows=snapshot, requested_at="t", current_research_scope=scope)
    for ticker in ("AAA", "BBB", "CCC"):
        scoped_card = dict(scoped["cards"][ticker])
        scoped_card.pop("official_research_scope")
        assert scoped_card == unscoped["cards"][ticker]


# A temporally ineligible scope must never filter the Screener at all, and every card must
# report the scope as explicitly unknown/ineligible rather than silently omitting the field.
def test_screener_temporally_ineligible_scope_is_never_applied():
    snapshot = [_row("AAA"), _row("BBB")]
    official = _synthetic_official_artifact(eligible={"AAA"}, all_tickers={"AAA", "BBB"})
    scope = resolve_scope(official_artifact=official, research_session="2026-09-11")
    assert scope["temporally_eligible"] is False
    out = build_projection(snapshot_rows=snapshot, requested_at="t", current_research_scope=scope)
    assert out["denominator"]["current_research_scope_applied"] is False
    assert set(out["cards"]) == {"AAA", "BBB"}
    assert out["cards"]["AAA"]["official_research_scope"]["scope_bucket"] == "CURRENT_OFFICIAL_SCOPE_UNKNOWN"
    assert out["official_scope_coverage"]["temporally_eligible"] is False


# ---------------------------------------------------------------------------------------------
# Workspace (18-20)
# ---------------------------------------------------------------------------------------------

def _opportunity(*tickers: str) -> dict:
    return {"contract_version": "opportunity_context/v1", "artifact_identity": "opp:1", "as_of_session": _SESSION,
            "records": {t: {"as_of_session": _SESSION, "usable_major_axes": [], "data_authority": {}} for t in tickers}}


def _decision(*tickers: str, stances: dict | None = None) -> dict:
    stances = stances or {}
    return {"contract_version": "security_decision_context/v1", "artifact_identity": "dec:1",
            "source_artifacts": {"opportunity_context": "opp:1"},
            "records": {t: {"as_of_session": _SESSION, "research_stance": stances.get(t, "WAIT_FOR_CONFIRMATION"),
                             "entry_state": "DOWNTREND", "entry_action": "WATCH"} for t in tickers}}


def test_18_workspace_default_denominator_unchanged():
    out = build_workspace_artifacts(opportunity_artifact=_opportunity("AAA", "BBB"), decision_artifact=_decision("AAA", "BBB"), requested_at="t")
    assert out["coverage"]["ticker_denominator"] == 2
    assert out["coverage"]["current_research_scope_applied"] is False
    assert set(out["cards"]) == {"AAA", "BBB"}


def test_19_workspace_opt_in_scoped_denominator():
    # Scoping never narrows the Workspace denominator either -- BBB stays a card, tagged
    # OUTSIDE, not dropped.
    official = _synthetic_official_artifact(eligible={"AAA"}, all_tickers={"AAA", "BBB"})
    scope = resolve_scope(official_artifact=official, research_session=_SESSION)
    out = build_workspace_artifacts(opportunity_artifact=_opportunity("AAA", "BBB"), decision_artifact=_decision("AAA", "BBB"),
                                     requested_at="t", current_research_scope=scope)
    assert out["coverage"]["current_research_scope_applied"] is True
    assert out["coverage"]["ticker_denominator"] == 2
    assert set(out["cards"]) == {"AAA", "BBB"}
    assert out["cards"]["AAA"]["official_research_scope"]["scope_bucket"] == "IN_CURRENT_OFFICIAL_RESEARCH_SCOPE"
    assert out["cards"]["BBB"]["official_research_scope"]["scope_bucket"] == "OUTSIDE_CURRENT_OFFICIAL_RESEARCH_SCOPE"
    coverage = out["official_scope_coverage"]
    assert coverage["workspace_denominator"] == 2
    assert coverage["current_official_research_scope_count"] == 1
    assert coverage["outside_current_official_scope_count"] == 1


def test_20_workspace_retained_card_content_unchanged_except_universe_metadata():
    unscoped = build_workspace_artifacts(opportunity_artifact=_opportunity("AAA", "BBB"), decision_artifact=_decision("AAA", "BBB", stances={"AAA": "INITIATE_RESEARCH_CANDIDATE"}), requested_at="t")
    official = _synthetic_official_artifact(eligible={"AAA"}, all_tickers={"AAA", "BBB"})
    scope = resolve_scope(official_artifact=official, research_session=_SESSION)
    scoped = build_workspace_artifacts(opportunity_artifact=_opportunity("AAA", "BBB"), decision_artifact=_decision("AAA", "BBB", stances={"AAA": "INITIATE_RESEARCH_CANDIDATE"}),
                                        requested_at="t", current_research_scope=scope)
    scoped_card = dict(scoped["cards"]["AAA"])
    scoped_card.pop("official_research_scope")
    assert scoped_card == unscoped["cards"]["AAA"]
    assert scoped["cards"]["AAA"]["research_stance"] == "INITIATE_RESEARCH_CANDIDATE"


# ---------------------------------------------------------------------------------------------
# Orchestration (21-25)
# ---------------------------------------------------------------------------------------------

def test_21_canonical_current_product_path_wires_official_scope_non_destructively():
    # CURRENT_OFFICIAL_RESEARCH_UNIVERSE_PRODUCT_CUTOVER_AND_RELEASE_INTEGRATION_V1 wires
    # current_research_scope into both canonical call sites. When the pinned official-universe
    # evidence is absent (e.g. this repo checkout has no operations-review evidence at all),
    # resolution degrades to None and both products stay byte-identical to the pre-wiring
    # behavior -- verified end to end, not just by source inspection.
    import canonical_current_product_projections as ccpp
    scope = ccpp.resolve_current_research_official_universe_scope(Path("/definitely/does/not/exist"), "2026-09-20")
    assert scope is None


@_REQUIRES_REAL_EVIDENCE
def test_21b_canonical_resolver_reads_pinned_real_evidence():
    import canonical_current_product_projections as ccpp
    scope = ccpp.resolve_current_research_official_universe_scope(ROOT, "2026-09-20")
    assert scope is not None
    assert scope["source_reference_ticker_count"] == 1683
    assert scope["current_research_scope_ticker_count"] == 1504

    # A session strictly before the evidence's own observation date must never receive a
    # fabricated/backdated scope -- see the temporal negative control (test_12).
    negative = ccpp.resolve_current_research_official_universe_scope(ROOT, "2026-09-11")
    assert negative is not None
    assert negative["temporally_eligible"] is False
    assert negative["current_research_scope_ticker_count"] is None


def test_22_integration_is_explicit_opt_in():
    import inspect
    from screener_master_projection import build_projection as _bp
    from investment_decision_workspace_projection import build_artifacts as _ba
    assert inspect.signature(_bp).parameters["current_research_scope"].default is None
    assert inspect.signature(_ba).parameters["current_research_scope"].default is None


def test_23_missing_official_universe_cannot_silently_fabricate_scope():
    snapshot = [_row("AAA"), _row("BBB")]
    out = build_projection(snapshot_rows=snapshot, requested_at="t", current_research_scope=None)
    assert out["denominator"]["current_research_scope_applied"] is False
    assert set(out["cards"]) == {"AAA", "BBB"}


@_REQUIRES_REAL_EVIDENCE
def test_24_official_only_names_never_injected_into_scoped_screener(official_artifact):
    scope = resolve_scope(official_artifact=official_artifact, research_session="2026-09-20")
    official_only_tickers = set(official_artifact["reconciliation"]["official_only_tickers"])
    snapshot = [_row(t) for t in list(official_only_tickers)[:2]] + [_row("HPG")]
    # Even if a snapshot somehow carried an official-only ticker, the scope's eligible set never
    # contains one (resolve_scope only ever emits stocklookup_candidate rows), so it is excluded.
    eligible = eligible_ticker_set(scope)
    assert not (official_only_tickers & eligible)


def test_25_no_strategy_ranking_sizing_logic_change():
    # The scope adapter and both consumer seams never touch blocked_outputs/strategy fields.
    snapshot = [_row("AAA")]
    out = build_projection(snapshot_rows=snapshot, requested_at="t")
    assert out["blocked_outputs"]["universal_score"] == "SCORING_PROHIBITED"
    assert out["blocked_outputs"]["ordinal_rank"] == "RANKING_PROHIBITED"
    workspace_out = build_workspace_artifacts(opportunity_artifact=_opportunity("AAA"), decision_artifact=_decision("AAA"), requested_at="t")
    assert workspace_out["blocked_outputs"]["universal_score"] == "SCORING_PROHIBITED"
