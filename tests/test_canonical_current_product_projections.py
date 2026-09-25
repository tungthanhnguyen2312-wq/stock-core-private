"""Focused tests for canonical_current_product_projections.py.

Root cause under test: screener_master_projection.json and
investment_decision_workspace_projection.json were each materialized exactly once by a
hand-run, milestone-dated tool and never regenerated since -- see
docs/dashboard_current_session_surface_coherence_20260912.md (Dashboard repository). This
module is the session-parametric, no-search materialization boundary that replaces those
one-off tools for the recurring canonical path.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import canonical_current_product_projections as ccpp
from test_investment_decision_workspace_projection import (
    _artifact, valuation_record, watchlist as _watchlist_record,
)

from _integrated_decision_fixture import integrated_decision as _integrated_decision

SESSION = "2026-09-11"
OTHER_SESSION = "2026-08-28"


def _integrated_for(session, registry_inputs):
    """The Workspace's required action-decision authority, built by the production builder over
    exactly the Daily denominator (watchlist | valuation) the Workspace itself uses."""
    registry_inputs = registry_inputs or {}
    tickers = set(((registry_inputs.get("tactical") or {}).get("records") or {})) | set(
        ((registry_inputs.get("valuation") or {}).get("records") or {})
    )
    return _integrated_decision(session, tickers) if tickers else None


def _materialize_workspace(**kwargs):
    kwargs.setdefault("integrated_investment_decision_product", _integrated_for(kwargs["session"], kwargs.get("registry_inputs")))
    return ccpp.materialize_current_investment_decision_workspace(**kwargs)


def _materialize_and_write(**kwargs):
    kwargs.setdefault("integrated_investment_decision_product", _integrated_for(kwargs["session"], kwargs.get("registry_inputs")))
    return ccpp.materialize_and_write_current_product_projections(**kwargs)


def _watchlist_artifact(tickers=("AAA", "BBB"), *, session=SESSION):
    records = {t: _watchlist_record(t) for t in tickers}
    return _artifact(records, session=session, kind="watch")


def _valuation_artifact(tickers=("AAA", "BBB"), *, session=SESSION):
    records = {t: valuation_record(t) for t in tickers}
    return {"valuation_session": session, "artifact_identity": f"current_valuation:{session}", "records": records}


def _registry_inputs(tickers=("AAA", "BBB"), *, session=SESSION):
    return {
        "tactical": _watchlist_artifact(tickers, session=session),
        "valuation": _valuation_artifact(tickers, session=session),
        "event_context": None,
        "official_universe": None,
    }


def _snapshot_csv(path: Path, tickers=("AAA", "BBB")) -> None:
    rows = "\n".join(f"{t},HSX,{SESSION}" for t in tickers)
    path.write_text(f"ticker,exchange,date\n{rows}\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# resolve_supplementary_inputs -- explicit, deterministic, no search
# ---------------------------------------------------------------------------

def test_resolve_supplementary_inputs_reads_exact_deterministic_path(tmp_path):
    session_dir = tmp_path / "operations-review" / "current-market-sector-leadership-context-v1-20260911"
    session_dir.mkdir(parents=True)
    payload = {"artifact_identity": "leadership:1", "session": SESSION}
    (session_dir / "current_market_sector_leadership_context_artifact.json").write_text(
        json.dumps(payload), encoding="utf-8",
    )
    resolved = ccpp.resolve_supplementary_inputs(tmp_path, SESSION)
    assert resolved["leadership"] == payload


def test_resolve_supplementary_inputs_missing_axis_is_none_not_an_error(tmp_path):
    resolved = ccpp.resolve_supplementary_inputs(tmp_path, SESSION)
    assert resolved == {name: None for name in ccpp.SUPPLEMENTARY_INPUT_TEMPLATES}


def test_resolve_supplementary_inputs_never_falls_back_to_a_different_session(tmp_path):
    stale_dir = tmp_path / "operations-review" / "current-market-sector-leadership-context-v1-20260828"
    stale_dir.mkdir(parents=True)
    (stale_dir / "current_market_sector_leadership_context_artifact.json").write_text(
        json.dumps({"artifact_identity": "leadership:stale", "session": OTHER_SESSION}), encoding="utf-8",
    )
    resolved = ccpp.resolve_supplementary_inputs(tmp_path, SESSION)
    assert resolved["leadership"] is None


# ---------------------------------------------------------------------------
# resolve_velocity_and_flow_price_inputs -- separate directory convention, same fail-closed
# contract as resolve_supplementary_inputs.
# ---------------------------------------------------------------------------

def test_resolve_velocity_and_flow_price_inputs_reads_exact_deterministic_path(tmp_path):
    velocity_dir = tmp_path / "operations-review" / "multi-session-signal-velocity-v1.2" / SESSION
    velocity_dir.mkdir(parents=True)
    payload = {"artifact_identity": "multi_session_signal_velocity:1", "records": []}
    (velocity_dir / "multi_session_signal_velocity_artifact.json").write_text(json.dumps(payload), encoding="utf-8")
    resolved = ccpp.resolve_velocity_and_flow_price_inputs(tmp_path, SESSION)
    assert resolved["signal_velocity"] == payload
    assert resolved["flow_price"] is None


def test_resolve_velocity_and_flow_price_inputs_missing_is_none_not_an_error(tmp_path):
    resolved = ccpp.resolve_velocity_and_flow_price_inputs(tmp_path, SESSION)
    assert resolved == {"signal_velocity": None, "flow_price": None}


def test_resolve_velocity_and_flow_price_inputs_never_falls_back_to_a_different_session(tmp_path):
    stale_dir = tmp_path / "operations-review" / "flow-price-divergence-shadow-v1" / OTHER_SESSION
    stale_dir.mkdir(parents=True)
    (stale_dir / "flow_price_divergence_shadow_artifact.json").write_text(
        json.dumps({"artifact_identity": "flow_price_divergence_shadow:stale"}), encoding="utf-8",
    )
    resolved = ccpp.resolve_velocity_and_flow_price_inputs(tmp_path, SESSION)
    assert resolved["flow_price"] is None


def test_resolve_flow_research_cohort_tickers_reads_real_owner_focus_config():
    """This resolves the actual repo-tracked config, not a fixture -- the cohort must contain
    the real 11-ticker broader_watchlist (HPG et al.), never an empty/fabricated set."""
    cohort = ccpp.resolve_flow_research_cohort_tickers()
    assert "HPG" in cohort
    assert len(cohort) == 11


# ---------------------------------------------------------------------------
# materialize_current_investment_decision_workspace
# ---------------------------------------------------------------------------

def test_workspace_as_of_session_matches_the_explicit_session_parameter_not_a_hardcoded_date():
    bundle = _materialize_workspace(
        session=SESSION, registry_inputs=_registry_inputs(), supplementary={},
        requested_at="2026-09-11T18:00:00+07:00",
    )
    assert bundle["workspace"]["as_of_session"] == SESSION
    assert "2026-08-28" not in json.dumps(bundle["workspace"])


def test_workspace_works_for_an_arbitrary_session_parameter_not_just_2026_09_11():
    other = "2026-09-04"
    bundle = _materialize_workspace(
        session=other, registry_inputs=_registry_inputs(session=other), supplementary={},
        requested_at=f"{other}T18:00:00+07:00",
    )
    assert bundle["workspace"]["as_of_session"] == other


def test_workspace_raises_when_required_registry_inputs_are_missing():
    with pytest.raises(ccpp.CanonicalCurrentProductProjectionsError):
        _materialize_workspace(
            session=SESSION, registry_inputs={}, supplementary={}, requested_at="2026-09-11T18:00:00+07:00",
        )


def test_workspace_no_ticker_silently_drops():
    tickers = ("AAA", "BBB", "CCC")
    bundle = _materialize_workspace(
        session=SESSION, registry_inputs=_registry_inputs(tickers), supplementary={},
        requested_at="2026-09-11T18:00:00+07:00",
    )
    assert set(bundle["workspace"]["cards"]) == set(tickers)
    assert bundle["workspace"]["coverage"]["zero_silent_ticker_drops"] is True


def test_workspace_missing_liquidity_axis_remains_unavailable_not_fabricated():
    bundle = _materialize_workspace(
        session=SESSION, registry_inputs=_registry_inputs(), supplementary={"liquidity": None},
        requested_at="2026-09-11T18:00:00+07:00",
    )
    for card in bundle["workspace"]["cards"].values():
        assert card["liquidity"]["readiness"] != "LIQUIDITY_RESEARCH_PROXY"  # never fabricated from nothing


def test_workspace_portfolio_unavailable_stays_not_evaluated_never_a_share_count():
    bundle = _materialize_workspace(
        session=SESSION, registry_inputs=_registry_inputs(), supplementary={},
        requested_at="2026-09-11T18:00:00+07:00",
    )
    for card in bundle["workspace"]["cards"].values():
        assert card["portfolio"]["status"] == "NOT_EVALUATED"
        assert card["portfolio"].get("evaluated") is not True
        assert card["portfolio"]["reason"] == "NO_PORTFOLIO_RESEARCH_CONTEXT_SUPPLIED"


def test_workspace_threads_supplementary_velocity_and_flow_price_into_every_card():
    velocity_artifact = {
        "contract_version": "multi_session_signal_velocity/v1.2",
        "artifact_identity": "multi_session_signal_velocity:test",
        "records": [{
            "ticker": "AAA", "session": SESSION, "overall_transition_state": "EARLY_IMPROVEMENT",
            "evidence_quality": {"state": "PARTIAL_RETAINED_EVIDENCE"}, "axes": {},
            "independent_supporting_axes": [], "contradicting_axes": [],
        }],
    }
    bundle = _materialize_workspace(
        session=SESSION, registry_inputs=_registry_inputs(tickers=("AAA", "BBB")),
        supplementary={"signal_velocity": velocity_artifact, "flow_price": None},
        requested_at="2026-09-11T18:00:00+07:00",
    )
    cards = bundle["workspace"]["cards"]
    assert cards["AAA"]["signal_velocity"]["overall_transition_state"] == "EARLY_IMPROVEMENT"
    assert cards["BBB"]["signal_velocity"]["overall_transition_state"] == "INSUFFICIENT_EVIDENCE"
    assert cards["AAA"]["flow_price"]["relationship"] == "FLOW_UNAVAILABLE"
    # The real owner-focus cohort (HPG et al.) never includes fixture tickers AAA/BBB.
    assert cards["AAA"]["flow_price"]["cohort_membership"] == "OUTSIDE_CURRENT_FLOW_RESEARCH_COHORT"


def _write_value_observation(runtime_root, ticker, session, *, buy=100, sell=40):
    # Raw store shape (current_foreign_flow_retention.write_exact_value_observation): keys are
    # NOT _vnd-suffixed on disk -- dnse_foreign_flow_store.build_series re-projects them through
    # _value_observation() to the _vnd-suffixed shape on read.
    import dnse_foreign_flow_store as store
    store.write_observations(runtime_root, ticker, [{
        "ticker": ticker, "session_date": session, "observed_at": f"{session} 15:00:00.000",
        "foreign_buy_value": buy, "foreign_sell_value": sell, "foreign_net_value": buy - sell,
        "source": store.PROVIDER, "source_contract_version": store.SOURCE_CONTRACT_VERSION,
        "value_unit": "vnd", "provenance": {}, "qualification_status": store.VALUE_QUALIFICATION_STATUS,
        "warnings": [],
    }])


def test_flow_price_prefers_operation_linked_current_evidence_over_a_stale_static_artifact(tmp_path, monkeypatch):
    """FLOW_PRICE_CANONICAL_SOURCE_BACKFILL_AND_PRESENTATION_CORRECTIVE_V1 regression: a stale
    pre-live flow_price_divergence_shadow_artifact.json supplied via ``supplementary`` (the old
    resolution path) must never be consumed for presentation once a newer, independently-
    verifiable current-session VALUE observation exists in the runtime store. This must fail if
    the fix regresses to reading only the stale static artifact.

    ``monkeypatch.setenv`` overrides conftest.py's session-wide STOCK_LOOKUP_RUNTIME_ROOT (which
    points every test at the shared dashboard-runtime checkout) so this test's VALUE store lives
    under its own isolated ``tmp_path``, exactly like the other runtime-dependent tests in this
    file already do.
    """
    monkeypatch.setenv("STOCK_LOOKUP_RUNTIME_ROOT", str(tmp_path))
    session = SESSION
    velocity_artifact = {
        "contract_version": "multi_session_signal_velocity/v1.2",
        "artifact_identity": "multi_session_signal_velocity:test",
        "records": [{
            "ticker": "HPG", "session": session, "overall_transition_state": "MIXED_TRANSITION",
            "evidence_quality": {"state": "COMPLETE_RETAINED_EVIDENCE"},
            "axes": {"structural_repair": {"trajectory": {}}},
            "independent_supporting_axes": [], "contradicting_axes": [],
        }],
    }
    # Real current-session VALUE evidence, independently verifiable via
    # current_foreign_flow_enrichment_operation.verify_ticker_current.
    _write_value_observation(tmp_path, "HPG", session, buy=520_495_564_350, sell=269_865_036_850)

    # A stale, pre-live static artifact claiming HPG is FLOW_UNAVAILABLE -- exactly the shape the
    # old (buggy) resolution path would have handed to presentation.
    stale_flow_price_artifact = {
        "contract_version": "flow_price_divergence_shadow/v1",
        "artifact_identity": "flow_price_divergence_shadow:stale-pre-live",
        "records": [{
            "ticker": "HPG", "reference_session": session,
            "flow": {"state": "FLOW_UNAVAILABLE"}, "price": {"state": "PRICE_EVIDENCE_INSUFFICIENT"},
            "relationship": "FLOW_UNAVAILABLE", "evidence_quality": "INSUFFICIENT_RETAINED_EVIDENCE",
            "session_alignment": {"state": "UNAVAILABLE"}, "limitations": [],
        }],
    }

    bundle = _materialize_workspace(
        session=session, registry_inputs=_registry_inputs(tickers=("HPG", "BBB"), session=session),
        supplementary={"signal_velocity": velocity_artifact, "flow_price": stale_flow_price_artifact},
        requested_at=f"{session}T18:00:00+07:00", root=tmp_path,
    )
    card = bundle["workspace"]["cards"]["HPG"]
    assert card["flow_price"]["relationship"] != "FLOW_UNAVAILABLE"
    assert card["flow_price"]["foreign_flow_state"] == "NET_FOREIGN_BUY"
    assert card["flow_price"]["cohort_membership"] == "IN_CURRENT_FLOW_RESEARCH_COHORT"


REPO_ROOT = Path(__file__).resolve().parents[1]
_LIVE_VELOCITY_PATH = REPO_ROOT / "operations-review" / "multi-session-signal-velocity-v1.2" / "2026-09-18" / "multi_session_signal_velocity_artifact.json"
_LIVE_ENRICHMENT_OPERATION_PATH = REPO_ROOT / "operations-review" / "current-foreign-flow-enrichment-v1" / "2026-09-18" / "current_foreign_flow_enrichment_operation.json"
_LIVE_OBSERVATIONS_DIR = REPO_ROOT / "data" / "dnse-foreign-flow" / "observations"


# Retained-evidence tier: the real retained 2026-09-18 live foreign-flow evidence.
@pytest.mark.retained_evidence(
    *(path.relative_to(REPO_ROOT).as_posix()
      for path in (_LIVE_VELOCITY_PATH, _LIVE_ENRICHMENT_OPERATION_PATH, _LIVE_OBSERVATIONS_DIR))
)
def test_real_2026_09_18_live_enrichment_reproduces_the_accepted_relationship_distribution(monkeypatch):
    """FLOW_PRICE_CANONICAL_SOURCE_BACKFILL_AND_PRESENTATION_CORRECTIVE_V1 real-artifact
    acceptance: rebuilding Flow-Price from the genuine retained 2026-09-18 live foreign-flow
    VALUE store (data/dnse-foreign-flow/observations/, independently re-verified via
    current_foreign_flow_enrichment_operation.verify_ticker_current) reproduces the owner's
    accepted 11/11 evaluable relationship distribution -- proving the root-caused presentation
    bug (resolving a stale pre-live static artifact) is fixed against real evidence, not just a
    synthetic fixture. This checkout's exact claimed artifact_identity
    (flow_price_divergence_shadow:6ed1974...) does not independently reproduce byte-for-byte and
    was not found anywhere in this repository's tracked history -- only the counted distribution
    is asserted here, not a specific identity hash.
    """
    monkeypatch.setenv("STOCK_LOOKUP_RUNTIME_ROOT", str(REPO_ROOT))
    velocity_artifact = json.loads(_LIVE_VELOCITY_PATH.read_text(encoding="utf-8"))
    cohort = ccpp.resolve_flow_research_cohort_tickers()
    artifact = ccpp.materialize_current_flow_price_divergence_shadow(
        root=REPO_ROOT, session="2026-09-18", velocity_artifact=velocity_artifact, flow_cohort_tickers=cohort,
    )
    assert artifact is not None
    assert artifact["validation"]["relationship_counts"] == {
        "FLOW_PRICE_MIXED": 7,
        "FOREIGN_BUYING_PRICE_WEAKNESS": 2,
        "FOREIGN_SELLING_PRICE_WEAKNESS": 2,
        "FLOW_UNAVAILABLE": 1672,
    }
    assert artifact["validation"]["relationship_evaluable_count"] == 11
    assert artifact["validation"]["current_exact_session_aligned_count"] == 11


def test_flow_price_degrades_gracefully_when_no_root_supplied():
    """Backward compatibility: omitting ``root`` (existing/older callers) must still produce an
    explicit unavailable Flow-Price, never a crash."""
    velocity_artifact = {
        "contract_version": "multi_session_signal_velocity/v1.2", "artifact_identity": "x",
        "records": [{"ticker": "HPG", "session": SESSION, "overall_transition_state": "STABLE",
                     "evidence_quality": {"state": "COMPLETE_RETAINED_EVIDENCE"}, "axes": {},
                     "independent_supporting_axes": [], "contradicting_axes": []}],
    }
    bundle = _materialize_workspace(
        session=SESSION, registry_inputs=_registry_inputs(tickers=("HPG",)),
        supplementary={"signal_velocity": velocity_artifact},
        requested_at="2026-09-11T18:00:00+07:00",
    )
    assert bundle["workspace"]["cards"]["HPG"]["flow_price"]["relationship"] == "FLOW_UNAVAILABLE"


# ---------------------------------------------------------------------------
# M1_LIVE_ACCEPTANCE_CORRECTIVE_V1 (Finding D): the 2026-09-24 post-handoff re-join passed the
# Dashboard runtime as ``runtime_root_override`` yet resolved the foreign-flow VALUE store through
# ``runtime_root(root)`` -- in the real in-process Daily STOCK_LOOKUP_RUNTIME_ROOT is unset, so that
# is the Producer checkout, whose local store ended 2026-09-18. The Workspace then showed 11/11
# FLOW_UNAVAILABLE although the release runtime held all 11 exact-session observations. The test
# session's conftest normally exports the variable, which is how this escaped; these tests remove it.
# ---------------------------------------------------------------------------

def _velocity(session, ticker="HPG"):
    return {
        "contract_version": "multi_session_signal_velocity/v1.2",
        "artifact_identity": "multi_session_signal_velocity:test",
        "records": [{"ticker": ticker, "session": session, "overall_transition_state": "MIXED_TRANSITION",
                     "evidence_quality": {"state": "COMPLETE_RETAINED_EVIDENCE"},
                     "axes": {"structural_repair": {"trajectory": {}}},
                     "independent_supporting_axes": [], "contradicting_axes": []}],
    }


def _split_roots(tmp_path, monkeypatch):
    """Producer-local store stale at an earlier session; the release runtime holds this session."""
    monkeypatch.delenv("STOCK_LOOKUP_RUNTIME_ROOT", raising=False)
    producer, runtime = tmp_path / "producer", tmp_path / "dashboard-runtime"
    _write_value_observation(producer, "HPG", OTHER_SESSION)
    _write_value_observation(runtime, "HPG", SESSION, buy=520_495_564_350, sell=269_865_036_850)
    return producer, runtime


def test_flow_price_reads_the_selected_release_runtime_not_the_producer_local_store(tmp_path, monkeypatch):
    producer, runtime = _split_roots(tmp_path, monkeypatch)
    kwargs = dict(session=SESSION, registry_inputs=_registry_inputs(tickers=("HPG", "BBB")),
                  supplementary={"signal_velocity": _velocity(SESSION)},
                  requested_at=f"{SESSION}T18:00:00+07:00", root=producer)

    selected = _materialize_workspace(runtime_root_override=runtime, **kwargs)["workspace"]["cards"]["HPG"]["flow_price"]
    assert selected["relationship"] != "FLOW_UNAVAILABLE"
    assert selected["foreign_flow_state"] == "NET_FOREIGN_BUY"
    assert selected["latest_qualified_flow_session"] == SESSION
    # The pre-fix resolution (no explicit runtime, variable unset) reads the stale Producer store.
    legacy = _materialize_workspace(**kwargs)["workspace"]["cards"]["HPG"]["flow_price"]
    assert legacy["relationship"] == "FLOW_UNAVAILABLE"


def test_top_level_rejoin_uses_its_runtime_root_override_for_every_runtime_read(tmp_path, monkeypatch):
    producer, runtime = _split_roots(tmp_path, monkeypatch)
    _snapshot_csv(runtime / "screen_snapshot.csv", tickers=("HPG", "BBB"))
    supplementary_dir = producer / "operations-review" / "multi-session-signal-velocity-v1.2" / SESSION
    supplementary_dir.mkdir(parents=True)
    (supplementary_dir / "multi_session_signal_velocity_artifact.json").write_text(json.dumps(_velocity(SESSION)), encoding="utf-8")

    result = _materialize_and_write(
        root=producer, session=SESSION, operation_dir=tmp_path / "presentation",
        registry_inputs=_registry_inputs(tickers=("HPG", "BBB")),
        requested_at=f"{SESSION}T18:00:00+07:00", runtime_root_override=runtime,
    )

    assert result["status"] == "MATERIALIZED"
    workspace = json.loads((tmp_path / "presentation" / ccpp.WORKSPACE_ARTIFACT_FILENAME).read_text(encoding="utf-8"))
    assert workspace["source_artifacts"]["flow_price_divergence_shadow"] is not None
    assert workspace["cards"]["HPG"]["flow_price"]["foreign_flow_state"] == "NET_FOREIGN_BUY"


def test_flow_observer_restaging_never_moves_posture_or_evidence_currency(tmp_path, monkeypatch):
    producer, runtime = _split_roots(tmp_path, monkeypatch)
    inputs = _registry_inputs(tickers=("HPG", "BBB"))
    integrated = _integrated_for(SESSION, inputs)
    common = dict(session=SESSION, registry_inputs=inputs, requested_at=f"{SESSION}T18:00:00+07:00",
                  root=producer, integrated_investment_decision_product=integrated)
    sealed = _materialize_workspace(supplementary={}, **common)["workspace"]["cards"]
    observed = _materialize_workspace(supplementary={"signal_velocity": _velocity(SESSION)},
                                      runtime_root_override=runtime, **common)["workspace"]["cards"]
    assert observed["HPG"]["flow_price"]["relationship"] != sealed["HPG"]["flow_price"]["relationship"]
    for ticker in sealed:
        for field in ("research_action_posture", "evidence_currency"):
            assert observed[ticker][field] == sealed[ticker][field] == integrated["records"][ticker][field]


def test_unavailable_recurring_axes_are_explicit_and_do_not_synthesize_a_contract():
    statuses = ccpp.unavailable_recurring_context_axes()
    assert statuses == {
        "portfolio": {
            "status": "NOT_EVALUATED",
            "reason_code": "NO_PORTFOLIO_RESEARCH_CONTEXT_SUPPLIED",
        },
    }
    bundle = _materialize_workspace(
        session=SESSION, registry_inputs=_registry_inputs(), supplementary={},
        requested_at="2026-09-11T18:00:00+07:00",
    )
    assert bundle["opportunity_context"]["source_artifacts"]["portfolio_research_context"] is None


def test_thesis_case_context_materializes_over_the_daily_denominator_even_with_no_fa_v2_or_events():
    """thesis_cases is no longer a permanently-unavailable axis (CANONICAL_EVIDENCE_BOUND_THESIS_
    CASES_DECISION_INPUT_V1): it now materializes from whatever financial_analysis_product_context/
    events are supplied, degrading individual tickers -- never the whole axis -- when both are
    absent, exactly like every other optional axis in this module."""
    bundle = _materialize_workspace(
        session=SESSION, registry_inputs=_registry_inputs(), supplementary={},
        requested_at="2026-09-11T18:00:00+07:00",
    )
    thesis_result = bundle["thesis_case_context"]
    assert thesis_result["status"] == "MATERIALIZED"
    artifact = thesis_result["artifact"]
    assert set(artifact["records"]) == {"AAA", "BBB"}
    assert artifact["coverage"]["zero_silent_ticker_drops"] is True
    # No FA V2/events supplied here -- every ticker legitimately has zero eligible cases, not a
    # fabricated one.
    assert artifact["coverage"]["tickers_with_zero_eligible_cases"] == 2
    assert bundle["opportunity_context"]["source_artifacts"]["thesis_catalyst_cases"] == artifact["artifact_identity"]


def test_workspace_prefers_registered_event_context_over_no_input_when_present():
    inputs = _registry_inputs()
    inputs["event_context"] = {"research_session": "2026-09-05", "artifact_identity": "evt:1", "records": {}}
    bundle = _materialize_workspace(
        session=SESSION, registry_inputs=inputs, supplementary={}, requested_at="2026-09-11T18:00:00+07:00",
    )
    assert bundle["opportunity_context"]["source_artifacts"]["corporate_event_context"] == "evt:1"


def test_workspace_wires_the_supplied_leadership_artifact_into_lineage():
    same_session_leadership = {
        "artifact_identity": "leadership:same-session", "session": SESSION,
        "ticker_contexts": {t: {"sector_leadership_context": {"group_key": "TECHNOLOGY"}} for t in ("AAA", "BBB")},
    }
    bundle = _materialize_workspace(
        session=SESSION, registry_inputs=_registry_inputs(), supplementary={"leadership": same_session_leadership},
        requested_at="2026-09-11T18:00:00+07:00",
    )
    # Lineage proves the supplied leadership artifact was actually passed through to both the
    # opportunity/decision join and the Workspace card build (not silently dropped) -- the
    # exact enrichment value additionally depends on leadership's own usability contract
    # (opportunity_axis_freshness.py), which is out of this module's scope to re-test.
    assert bundle["workspace"]["source_artifacts"]["market_sector_leadership"] == "leadership:same-session"
    assert bundle["opportunity_context"]["source_artifacts"]["market_sector_leadership"] == "leadership:same-session"


# ---------------------------------------------------------------------------
# materialize_current_screener_master_projection
# ---------------------------------------------------------------------------

def test_screener_master_as_of_session_is_the_explicit_session_never_derived_from_the_snapshot(tmp_path):
    snapshot_path = tmp_path / "screen_snapshot.csv"
    _snapshot_csv(snapshot_path)
    workspace_bundle = _materialize_workspace(
        session=SESSION, registry_inputs=_registry_inputs(), supplementary={},
        requested_at="2026-09-11T18:00:00+07:00",
    )
    artifact = ccpp.materialize_current_screener_master_projection(
        session=SESSION, root=tmp_path, snapshot_path=snapshot_path,
        workspace=workspace_bundle["workspace"], registry_inputs=_registry_inputs(), supplementary={},
        requested_at="2026-09-11T18:00:00+07:00",
    )
    assert artifact["as_of_session"] == SESSION


def test_screener_master_preserves_rows_even_when_financial_and_official_universe_are_absent(tmp_path):
    snapshot_path = tmp_path / "screen_snapshot.csv"
    _snapshot_csv(snapshot_path, tickers=("AAA", "BBB", "CCC"))
    workspace_bundle = _materialize_workspace(
        session=SESSION, registry_inputs=_registry_inputs(("AAA", "BBB", "CCC")), supplementary={},
        requested_at="2026-09-11T18:00:00+07:00",
    )
    artifact = ccpp.materialize_current_screener_master_projection(
        session=SESSION, root=tmp_path, snapshot_path=snapshot_path,
        workspace=workspace_bundle["workspace"], registry_inputs=_registry_inputs(("AAA", "BBB", "CCC")),
        supplementary={}, requested_at="2026-09-11T18:00:00+07:00",
    )
    assert set(artifact["cards"]) == {"AAA", "BBB", "CCC"}
    assert artifact["coverage"]["zero_silent_drops"] is True


# ---------------------------------------------------------------------------
# materialize_and_write_current_product_projections -- top-level, never raises
# ---------------------------------------------------------------------------

def test_top_level_never_raises_and_reports_skipped_on_a_genuinely_missing_dependency(tmp_path):
    result = ccpp.materialize_and_write_current_product_projections(
        root=tmp_path, session=SESSION, operation_dir=tmp_path / "operation",
        registry_inputs={}, requested_at="2026-09-11T18:00:00+07:00",
    )
    assert result["status"] == "SKIPPED"
    assert not (tmp_path / "operation").exists() or not list((tmp_path / "operation").glob("*"))


def test_top_level_writes_matching_json_js_pair_and_workspace_file_on_success(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    _snapshot_csv(runtime_dir / "screen_snapshot.csv")
    monkeypatch.setenv("STOCK_LOOKUP_RUNTIME_ROOT", str(runtime_dir))

    operation_dir = tmp_path / "operation"
    result = _materialize_and_write(
        root=tmp_path, session=SESSION, operation_dir=operation_dir,
        registry_inputs=_registry_inputs(), requested_at="2026-09-11T18:00:00+07:00",
    )
    assert result["status"] == "MATERIALIZED"
    assert result["workspace"]["as_of_session"] == SESSION
    assert result["screener_master_projection"]["as_of_session"] == SESSION
    assert result["context_axes"] == ccpp.unavailable_recurring_context_axes()
    assert result["thesis_case_context"]["status"] == "MATERIALIZED"
    assert "thesis_cases" not in result["unavailable_optional_axes"]
    thesis_on_disk = json.loads((operation_dir / ccpp.THESIS_CASE_CONTEXT_ARTIFACT_FILENAME).read_text(encoding="utf-8"))
    assert thesis_on_disk["artifact_identity"] == result["thesis_case_context"]["artifact_identity"]

    workspace_on_disk = json.loads((operation_dir / ccpp.WORKSPACE_ARTIFACT_FILENAME).read_text(encoding="utf-8"))
    screener_json_on_disk = json.loads((operation_dir / ccpp.SCREENER_MASTER_JSON_FILENAME).read_text(encoding="utf-8"))
    screener_js_text = (operation_dir / ccpp.SCREENER_MASTER_JS_FILENAME).read_text(encoding="utf-8")
    assert workspace_on_disk["as_of_session"] == SESSION
    assert screener_json_on_disk["as_of_session"] == SESSION
    # JSON/JS pair: same contract version, same as_of_session, same artifact identity -- one
    # logical projection, not two independently-sourced files.
    assert screener_js_text.startswith("window.SCREENER_MASTER_PROJECTION = ")
    js_payload = json.loads(screener_js_text[len("window.SCREENER_MASTER_PROJECTION = "):].rstrip("\n;".__add__(";")).rstrip(";"))
    assert js_payload["as_of_session"] == screener_json_on_disk["as_of_session"]
    assert js_payload["artifact_identity"] == screener_json_on_disk["artifact_identity"]
    assert js_payload["contract_version"] == screener_json_on_disk["contract_version"]


def test_no_hardcoded_decision_session_default_in_this_module():
    """The historical one-off tools hardcode ``DECISION_SESSION = "2026-08-28"``-style
    defaults; this module must never do the same -- session always comes from the explicit
    ``session`` parameter every function takes. Mentioning the date in prose (explaining why
    this module exists) is fine; assigning it as a default value is not."""
    source = Path(ccpp.__file__).read_text(encoding="utf-8")
    assert '= "2026-08-28"' not in source
    assert "DECISION_SESSION" not in source


# ---------------------------------------------------------------------------
# Retained-evidence replay qualification (local-only; skips when this checkout has no
# generated operations-review evidence for the session -- e.g. a fresh worktree or hosted CI).
# See docs/canonical_current_product_projections_replay_20260912.md for the full report from
# a checkout that does have the retained 2026-09-11 evidence.
# ---------------------------------------------------------------------------

REPLAY_SESSION = "2026-09-11"


def _replay_root() -> Path:
    return Path(__file__).resolve().parents[1]


# Retained-evidence tier: replays the real retained 2026-09-11 operations-review evidence.
@pytest.mark.retained_evidence(
    "operations-review/watchlist-tactical-entry-decision-v1-20260911/watchlist_tactical_entry_classifier_artifact.json"
)
def test_retained_2026_09_11_replay_materializes_genuinely_current_products(tmp_path, monkeypatch):
    root = _replay_root()
    from daily_research_session_operations import load_registry, resolve_inputs

    registry = load_registry(root)
    registry_inputs, _entries = resolve_inputs(root, REPLAY_SESSION, registry)
    runtime_root_env = Path(r"C:\Projects\StockLookup\dashboard-runtime")
    if not (runtime_root_env / "screen_snapshot.csv").is_file():
        pytest.skip("retained dashboard-runtime screen_snapshot.csv not present on this machine")
    monkeypatch.setenv("STOCK_LOOKUP_RUNTIME_ROOT", str(runtime_root_env))

    operation_dir = tmp_path / "replay_operation"
    result = ccpp.materialize_and_write_current_product_projections(
        root=root, session=REPLAY_SESSION, operation_dir=operation_dir,
        registry_inputs=registry_inputs, requested_at=f"{REPLAY_SESSION}T18:00:00+07:00",
        integrated_investment_decision_product=json.loads(
            (root / "operations-review" / "canonical-post-close-v1" / REPLAY_SESSION / "enrichment"
             / "integrated_investment_decision_product.json").read_text(encoding="utf-8")
        ),
    )
    assert result["status"] == "MATERIALIZED"
    assert result["workspace"]["as_of_session"] == REPLAY_SESSION
    assert result["screener_master_projection"]["as_of_session"] == REPLAY_SESSION
    assert result["workspace"]["ticker_denominator"] > 1000
    assert result["screener_master_projection"]["denominator"]["ticker_count"] > 1000
