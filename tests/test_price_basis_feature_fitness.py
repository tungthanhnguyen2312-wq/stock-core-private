"""Synthetic regressions for PRICE_BASIS_SEMANTICS_AND_FEATURE_FITNESS_V1."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import feature_input_fitness_contract as registry
import price_basis_feature_fitness as basis
from tools import run_price_basis_semantics_diagnostic as diagnostic


def _factor_chain(*, cutoff: str = "2025-01-10T12:00:00Z") -> dict:
    return {
        "identity": "factor-chain:verified-split-bonus-dividend",
        "status": "QUALIFIED",
        "official_execution_status": "EXECUTED",
        "ex_date_status": "EXPLICIT_OFFICIAL",
        "knowledge_cutoff": cutoff,
        "event_types": ["stock_split", "bonus_share", "cash_dividend"],
    }


def _context(
    selected_basis: str = basis.CURRENT_RETROSPECTIVE_ADJUSTED,
    *,
    lineage: str = "series:adjusted-current",
    factor_chain: dict | None = None,
) -> dict:
    return basis.price_series_context(
        ticker="SYN",
        provider="DNSE",
        source_identity="source:synthetic",
        session_start="2025-01-02",
        session_end="2025-01-31",
        observed_basis=selected_basis,
        basis_provenance=("synthetic-retained-source",),
        basis_confidence="SYNTHETIC_TEST_ONLY",
        basis_lineage_identity=lineage,
        adjustment_knowledge_cutoff=(factor_chain or {}).get("knowledge_cutoff"),
        factor_chain=factor_chain,
    )


def test_raw_and_adjusted_histories_can_differ_materially_without_numeric_gate() -> None:
    """A 25% post-action difference is an anomaly, not evidence of corruption by itself."""
    raw_price, adjusted_price = 100.0, 75.0
    assert abs(adjusted_price / raw_price - 1.0) > 0.15
    adjusted = _context(basis.POINT_IN_TIME_ADJUSTED, factor_chain=_factor_chain())
    result = basis.evaluate_feature_fitness(
        feature=basis.MA20, current_context=adjusted, history_context=adjusted,
        observed_price_divergence_pct=adjusted_price / raw_price - 1.0,
    )
    assert result["state"] == basis.BASIS_COMPATIBLE
    assert result["numeric_divergence"]["authority_gate"] is False
    assert basis.REASON_NUMERIC_DIVERGENCE_ANOMALY_ONLY in result["numeric_divergence"]["reason_codes"]


def test_verified_split_bonus_dividend_chain_permits_same_basis_technical_comparison() -> None:
    context = _context(basis.POINT_IN_TIME_ADJUSTED, factor_chain=_factor_chain())
    result = basis.evaluate_feature_fitness(
        feature=basis.RSI, current_context=context, history_context=context,
    )
    assert result["state"] == basis.BASIS_COMPATIBLE
    assert context["corporate_action_factor_chain"]["event_types"] == ["bonus_share", "cash_dividend", "stock_split"]


def test_future_corporate_action_is_rejected_for_prior_pit_decision() -> None:
    future_chain = _factor_chain(cutoff="2025-02-01T12:00:00Z")
    context = _context(basis.POINT_IN_TIME_ADJUSTED, factor_chain=future_chain)
    result = basis.evaluate_feature_fitness(
        feature=basis.PIT_BACKTEST, current_context=context, history_context=context,
        decision_as_of="2025-01-15T16:00:00Z",
    )
    assert result["state"] == basis.POINT_IN_TIME_SEMANTICS_UNQUALIFIED
    assert result["reason_codes"] == [basis.REASON_PIT_FACTOR_AFTER_DECISION]


def test_raw_execution_replay_rejects_adjusted_only_history() -> None:
    adjusted = _context()
    result = basis.evaluate_feature_fitness(
        feature=basis.EXECUTION_RAW_REPLAY, current_context=adjusted, history_context=adjusted,
    )
    assert result["state"] == basis.BASIS_INCOMPATIBLE
    assert result["reason_codes"] == [basis.REASON_EXECUTION_REQUIRES_RAW]


def test_current_adjusted_ma_is_research_valid_while_raw_authority_stays_unpromoted() -> None:
    adjusted = _context()
    result = registry.evaluate_price_derived_basis_fitness(
        feature=basis.MA20, current_context=adjusted, history_context=adjusted,
    )
    assert result["state"] == basis.BASIS_COMPATIBLE_RESEARCH_ONLY
    assert adjusted["raw_as_traded_authority"] == "NOT_PROMOTED"


def test_unknown_event_or_basis_provenance_fails_closed() -> None:
    unknown = basis.price_series_context(
        ticker="SYN", provider=None, source_identity=None, session_start=None, session_end=None,
        observed_basis="made_up_basis", basis_provenance=(),
    )
    result = basis.evaluate_feature_fitness(feature=basis.MA200, current_context=unknown)
    assert result["state"] == basis.BASIS_UNVERIFIED
    assert basis.REASON_BASIS_UNKNOWN in result["reason_codes"]
    assert basis.REASON_PROVENANCE_MISSING in result["reason_codes"]


def test_record_date_never_becomes_ex_date_or_factor() -> None:
    record_date_only = {
        "identity": "factor-chain:record-date-only",
        "status": "QUALIFIED",
        "official_execution_status": "EXECUTED",
        "record_date": "2025-01-20",
        # Intentionally no ex_date / ex_date_status.
    }
    context = _context(basis.POINT_IN_TIME_ADJUSTED, factor_chain=record_date_only)
    assert context["corporate_action_factor_chain"]["status"] == "UNQUALIFIED"
    assert basis.REASON_RECORD_DATE_NOT_EX_DATE in context["corporate_action_factor_chain"]["reason_codes"]
    result = basis.evaluate_feature_fitness(
        feature=basis.PIT_BACKTEST, current_context=context, decision_as_of="2025-01-21T00:00:00Z",
    )
    assert result["state"] == basis.POINT_IN_TIME_SEMANTICS_UNQUALIFIED
    assert result["reason_codes"] == [basis.REASON_PIT_FACTOR_CHAIN_UNQUALIFIED]


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_retained_diagnostic_reports_each_representative_ticker_without_daily_mutation(tmp_path: Path) -> None:
    session = "2026-01-30"
    descriptive = {
        "artifact_identity": "descriptive:fixture",
        "records": {
            ticker: {
                "ticker": ticker,
                "trend_state": "DOWNTREND" if ticker == "PAN" else "AT_OR_BELOW_MA20",
                "technical_features": {
                    "status": "SHADOW_ONLY", "feature_as_of_session": session,
                    "price_basis": "ADJUSTED_RETROSPECTIVE",
                    "technical_history_provenance": {"source": "RETAINED_FIXTURE"},
                    "feature_statuses": {"ma_20": "SHADOW_ONLY", "momentum_20d": "SHADOW_ONLY", "close": "OBSERVED"},
                    "values": {"close": 75.0, "ma_20": 100.0, "momentum_20d": -0.25},
                },
            }
            for ticker in diagnostic.REPRESENTATIVE_TICKERS
        },
    }
    corporate = {
        "artifact_identity": "corporate:fixture",
        "records": {ticker: {"corporate_action_context": {"events": [], "status": "UNAVAILABLE"}} for ticker in diagnostic.REPRESENTATIVE_TICKERS},
    }
    other = {"artifact_identity": "unused:fixture"}
    entries = {}
    for name in session_operations_required_names():
        path = Path("artifacts") / f"{name}.json"
        payload = descriptive if name == "descriptive" else corporate if name == "corporate_intelligence" else other
        _write_json(tmp_path / path, payload)
        entries[name] = {"path": str(path).replace("\\", "/"), "artifact_identity": payload["artifact_identity"]}
    _write_json(tmp_path / "config" / "daily_research_session_input_registry.json", {
        "contract_version": "daily_research_session_input_registry/v1",
        "sessions": {session: entries},
        "completed_sessions": {session: {
            "status": "COMPLETED_RETAINED_EVIDENCE", "frozen_input_identities": {name: entry["artifact_identity"] for name, entry in entries.items()},
        }},
    })
    artifact = diagnostic.build_diagnostic(runtime_root=tmp_path)
    assert set(artifact["cases"]) == {"SSI", "PNJ", "PAN"}
    assert artifact["cases"]["SSI"]["corporate_action_factor_chain"]["state"] == basis.BASIS_UNVERIFIED
    assert artifact["cases"]["SSI"]["current_vs_historical_basis"]["state"] == basis.BASIS_UNVERIFIED
    assert artifact["cases"]["PNJ"]["observed_series"]["numeric_divergence_authority_gate"] is False
    assert artifact["cases"]["PAN"]["existing_signal_context"]["trend_state"] == "DOWNTREND"
    assert artifact["authority_boundary"]["canonical_daily_classifications_modified"] is False


def session_operations_required_names() -> tuple[str, ...]:
    # Keep the fixture aligned with the existing registered-session contract instead of copying a
    # hand-maintained tuple into the test.
    import daily_research_session_operations
    return tuple(daily_research_session_operations.REQUIRED)
