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

SESSION = "2026-09-11"
OTHER_SESSION = "2026-08-28"


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
# materialize_current_investment_decision_workspace
# ---------------------------------------------------------------------------

def test_workspace_as_of_session_matches_the_explicit_session_parameter_not_a_hardcoded_date():
    bundle = ccpp.materialize_current_investment_decision_workspace(
        session=SESSION, registry_inputs=_registry_inputs(), supplementary={},
        requested_at="2026-09-11T18:00:00+07:00",
    )
    assert bundle["workspace"]["as_of_session"] == SESSION
    assert "2026-08-28" not in json.dumps(bundle["workspace"])


def test_workspace_works_for_an_arbitrary_session_parameter_not_just_2026_09_11():
    other = "2026-09-04"
    bundle = ccpp.materialize_current_investment_decision_workspace(
        session=other, registry_inputs=_registry_inputs(session=other), supplementary={},
        requested_at=f"{other}T18:00:00+07:00",
    )
    assert bundle["workspace"]["as_of_session"] == other


def test_workspace_raises_when_required_registry_inputs_are_missing():
    with pytest.raises(ccpp.CanonicalCurrentProductProjectionsError):
        ccpp.materialize_current_investment_decision_workspace(
            session=SESSION, registry_inputs={}, supplementary={}, requested_at="2026-09-11T18:00:00+07:00",
        )


def test_workspace_no_ticker_silently_drops():
    tickers = ("AAA", "BBB", "CCC")
    bundle = ccpp.materialize_current_investment_decision_workspace(
        session=SESSION, registry_inputs=_registry_inputs(tickers), supplementary={},
        requested_at="2026-09-11T18:00:00+07:00",
    )
    assert set(bundle["workspace"]["cards"]) == set(tickers)
    assert bundle["workspace"]["coverage"]["zero_silent_ticker_drops"] is True


def test_workspace_missing_liquidity_axis_remains_unavailable_not_fabricated():
    bundle = ccpp.materialize_current_investment_decision_workspace(
        session=SESSION, registry_inputs=_registry_inputs(), supplementary={"liquidity": None},
        requested_at="2026-09-11T18:00:00+07:00",
    )
    for card in bundle["workspace"]["cards"].values():
        assert card["liquidity"]["readiness"] != "LIQUIDITY_RESEARCH_PROXY"  # never fabricated from nothing


def test_workspace_portfolio_unavailable_stays_not_evaluated_never_a_share_count():
    bundle = ccpp.materialize_current_investment_decision_workspace(
        session=SESSION, registry_inputs=_registry_inputs(), supplementary={},
        requested_at="2026-09-11T18:00:00+07:00",
    )
    for card in bundle["workspace"]["cards"].values():
        assert card["portfolio"]["status"] == "NOT_EVALUATED"
        assert card["portfolio"].get("evaluated") is not True
        assert card["portfolio"]["reason"] == "NO_PORTFOLIO_RESEARCH_CONTEXT_SUPPLIED"


def test_unavailable_recurring_axes_are_explicit_and_do_not_synthesize_a_contract():
    statuses = ccpp.unavailable_recurring_context_axes()
    assert statuses == {
        "thesis_cases": {
            "status": "UNAVAILABLE",
            "reason_code": "CURRENT_THESIS_DECISION_INPUT_NOT_ESTABLISHED",
        },
        "portfolio": {
            "status": "NOT_EVALUATED",
            "reason_code": "NO_PORTFOLIO_RESEARCH_CONTEXT_SUPPLIED",
        },
    }
    bundle = ccpp.materialize_current_investment_decision_workspace(
        session=SESSION, registry_inputs=_registry_inputs(), supplementary={},
        requested_at="2026-09-11T18:00:00+07:00",
    )
    assert bundle["opportunity_context"]["source_artifacts"]["thesis_catalyst_cases"] is None
    assert bundle["opportunity_context"]["source_artifacts"]["portfolio_research_context"] is None


def test_workspace_prefers_registered_event_context_over_no_input_when_present():
    inputs = _registry_inputs()
    inputs["event_context"] = {"research_session": "2026-09-05", "artifact_identity": "evt:1", "records": {}}
    bundle = ccpp.materialize_current_investment_decision_workspace(
        session=SESSION, registry_inputs=inputs, supplementary={}, requested_at="2026-09-11T18:00:00+07:00",
    )
    assert bundle["opportunity_context"]["source_artifacts"]["corporate_event_context"] == "evt:1"


def test_workspace_wires_the_supplied_leadership_artifact_into_lineage():
    same_session_leadership = {
        "artifact_identity": "leadership:same-session", "session": SESSION,
        "ticker_contexts": {t: {"sector_leadership_context": {"group_key": "TECHNOLOGY"}} for t in ("AAA", "BBB")},
    }
    bundle = ccpp.materialize_current_investment_decision_workspace(
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
    workspace_bundle = ccpp.materialize_current_investment_decision_workspace(
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
    workspace_bundle = ccpp.materialize_current_investment_decision_workspace(
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
    result = ccpp.materialize_and_write_current_product_projections(
        root=tmp_path, session=SESSION, operation_dir=operation_dir,
        registry_inputs=_registry_inputs(), requested_at="2026-09-11T18:00:00+07:00",
    )
    assert result["status"] == "MATERIALIZED"
    assert result["workspace"]["as_of_session"] == SESSION
    assert result["screener_master_projection"]["as_of_session"] == SESSION
    assert result["context_axes"] == ccpp.unavailable_recurring_context_axes()

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


def _replay_evidence_present(root: Path) -> bool:
    return (root / "operations-review" / "watchlist-tactical-entry-decision-v1-20260911"
            / "watchlist_tactical_entry_classifier_artifact.json").is_file()


def test_retained_2026_09_11_replay_materializes_genuinely_current_products(tmp_path, monkeypatch):
    root = _replay_root()
    if not _replay_evidence_present(root):
        pytest.skip("retained 2026-09-11 operations-review evidence not present in this checkout")
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
    )
    assert result["status"] == "MATERIALIZED"
    assert result["workspace"]["as_of_session"] == REPLAY_SESSION
    assert result["screener_master_projection"]["as_of_session"] == REPLAY_SESSION
    assert result["workspace"]["ticker_denominator"] > 1000
    assert result["screener_master_projection"]["denominator"]["ticker_count"] > 1000
