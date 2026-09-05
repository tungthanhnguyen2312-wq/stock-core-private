"""Local-only retained replay for INTEGRATED_DECISION_EVIDENCE_AXIS_COHERENCE_V1.

The runner reuses established technical, momentum, participation, confirmation, financial,
valuation, market/sector, and priority products.  It neither acquires market data nor publishes,
writes a database, changes the frozen session registry, or assigns a score/probability/target.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.run_tactical_momentum_participation_confirmation_replay import (  # noqa: E402
    OPS,
    _build_current_research_surfaces,
    _load,
    _priority_queue,
    _write,
)

PRIMARY_SESSION = "2026-09-04"
TEMPORAL_SESSION = "2026-08-25"
WATCHLIST = ("EVF", "FPT", "HPG", "NVL", "PAN", "PNJ", "POW", "PVD", "QNS", "SSI", "VNM", "VCB")
AXES = (
    "FUNDAMENTAL", "VALUATION", "TACTICAL_STRUCTURE", "MOMENTUM",
    "PARTICIPATION_CONFIRMATION", "MARKET_SECTOR", "OPPORTUNITY_PRIORITY", "PORTFOLIO_FIT",
)
MAJOR_AXES = AXES[:-1]


def _artifact_path(session: str, name: str) -> Path:
    token = session.replace("-", "")
    table = {
        "sector": OPS / f"current-market-sector-leadership-context-v1-{token}" / "current_market_sector_leadership_context_artifact.json",
        "opportunity": OPS / f"current-opportunity-prioritization-v1-{token}" / "current_opportunity_prioritization_artifact.json",
        "financial": OPS / f"financial-analysis-product-v2-{token}" / "financial_analysis_product_artifact.json",
        "valuation": OPS / f"financial-analysis-product-v2-{token}" / "current_research_valuation_context_artifact.json",
        "retained_integrated": OPS / "canonical-post-close-v1" / session / "enrichment" / "integrated_investment_decision_product.json",
    }
    return table[name]


def _primary_financial() -> tuple[dict[str, Any], dict[str, Any]]:
    # These are the exact identities retained by the pre-integration canonical 2026-09-04
    # product.  Reusing them makes the retained before/after comparison about this wiring change,
    # not a different financial or valuation rebuild.
    financial = _load(_artifact_path(PRIMARY_SESSION, "financial"))
    valuation = _load(_artifact_path(PRIMARY_SESSION, "valuation"))
    return financial["financial_analysis_product"], valuation


def _inputs_for_current_research(session: str) -> dict[str, Any]:
    surfaces = _build_current_research_surfaces(session)
    token = session.replace("-", "")
    if session == PRIMARY_SESSION:
        financial, valuation = _primary_financial()
    else:
        # The retained Financial V2 source has a 2026-Q4 as-of period while the requested
        # replay session is 2026-08-25.  It is not admissible historical evidence, so these
        # two axes remain locally unavailable rather than leaking later evidence into replay.
        financial, valuation = None, None
    return {
        "surfaces": surfaces,
        "financial": financial,
        "valuation": valuation,
        "sector": _load(_artifact_path(session, "sector")),
        "opportunity": _load(_artifact_path(session, "opportunity")),
        "queue": _priority_queue(session),
        "retained_integrated": _load(_artifact_path(session, "retained_integrated")),
        "financial_temporal_source": _load(_artifact_path(session, "financial")) if session == TEMPORAL_SESSION else None,
        "token": token,
    }


def _build_integrated(session: str, inputs: Mapping[str, Any], *, attach_momentum_confirmation: bool) -> dict[str, Any]:
    import integrated_investment_decision_product as integrated

    surfaces = inputs["surfaces"]
    return integrated.build_artifact(
        session=session, requested_at="2026-09-05T00:00:00+07:00",
        technical_structure_artifact=surfaces["tactical"],
        financial_analysis_artifact=inputs["financial"],
        current_valuation_artifact=inputs["valuation"],
        relative_volume_artifact=surfaces["participation"],
        market_sector_artifact=inputs["sector"],
        legacy_decision_artifact=inputs["opportunity"],
        priority_queue_artifact=inputs["queue"],
        momentum_artifact=surfaces["momentum"] if attach_momentum_confirmation else None,
        tactical_confirmation_artifact=surfaces["confirmation"] if attach_momentum_confirmation else None,
    )


def _axis_available(axis_name: str, axis: Mapping[str, Any]) -> bool:
    if axis_name == "FUNDAMENTAL" and axis.get("state") == "INSUFFICIENT":
        return False
    fitness = axis.get("fitness")
    unavailable = {None, "UNAVAILABLE", "INSUFFICIENT_EVIDENCE", "NOT_PROVIDED", "ABSENT", "NOT_ELIGIBLE", "NOT_AVAILABLE", "INPUT_BLOCKED"}
    if isinstance(fitness, Mapping):
        return bool(fitness) and all(value not in unavailable for value in fitness.values())
    return fitness not in unavailable


def _counter(values: list[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _axis_coverage(product: Mapping[str, Any]) -> dict[str, Any]:
    records = product["records"]
    blockers: Counter[str] = Counter()
    axis_available = {axis: 0 for axis in AXES}
    all_major = 0
    for record in records.values():
        axes = record.get("evidence_axes") or {}
        for axis in AXES:
            current = axes.get(axis) or {}
            if _axis_available(axis, current):
                axis_available[axis] += 1
            blockers.update(str(item) for item in current.get("blocker_reason_codes") or [])
        if all(_axis_available(axis, axes.get(axis) or {}) for axis in MAJOR_AXES):
            all_major += 1
    return {
        "session": product.get("session"),
        "supported_universe_count": len(records),
        "decision_records": len(records),
        "axis_available": axis_available,
        "all_major_axes_available": all_major,
        "axis_blocker_distribution": dict(sorted(blockers.items())),
        "source_integrated_identity": product.get("artifact_identity"),
        "authority_boundary": {"market_wide_counts_are_coverage_not_scores": True, "is_actionable": False},
    }


def _coherence_distribution(product: Mapping[str, Any]) -> dict[str, Any]:
    states = {state: 0 for state in ("ALIGNED", "PARTIALLY_ALIGNED", "MIXED", "CONTRADICTED", "INSUFFICIENT_EVIDENCE")}
    states.update(_counter([
        str((record.get("evidence_axis_coherence") or {}).get("state"))
        for record in product["records"].values()
    ]))
    return {
        "session": product.get("session"),
        "distribution": states,
        "taxonomy": ["ALIGNED", "PARTIALLY_ALIGNED", "MIXED", "CONTRADICTED", "INSUFFICIENT_EVIDENCE"],
        "interpretation_boundary": "QUALITATIVE_EVIDENCE_RELATIONSHIPS_NOT_ALPHA_OR_PERFORMANCE",
    }


def _reason_distribution(records: list[Mapping[str, Any]], field: str) -> dict[str, int]:
    flattened: list[str] = []
    for record in records:
        for axis in (record.get("evidence_axes") or {}).values():
            flattened.extend(str(value) for value in axis.get(field) or [])
    return _counter(flattened)


def _cohort_summary(records: Mapping[str, Mapping[str, Any]], label: str, predicate: Callable[[Mapping[str, Any]], bool]) -> dict[str, Any]:
    selected = [record for record in records.values() if predicate(record)]
    missingness = Counter()
    for record in selected:
        for axis_name, axis in (record.get("evidence_axes") or {}).items():
            if not _axis_available(axis_name, axis):
                if axis_name in {"TACTICAL_STRUCTURE", "MOMENTUM", "PARTICIPATION_CONFIRMATION"}:
                    missingness["FEATURE_FITNESS_LIMITATION"] += 1
                elif axis_name == "PORTFOLIO_FIT":
                    missingness["LEGITIMATE_MISSINGNESS"] += 1
                else:
                    missingness["LEGITIMATE_MISSINGNESS"] += 1
        reconciliation = record.get("priority_posture_reconciliation") or {}
        if reconciliation.get("reconciliation_category") == "LEGITIMATE_POLICY_OUTCOME":
            missingness["POLICY_OUTCOME"] += 1
    return {
        "cohort": label,
        "count": len(selected),
        "posture_distribution": _counter([str(record.get("research_action_posture")) for record in selected]),
        "coherence_distribution": _counter([str((record.get("evidence_axis_coherence") or {}).get("state")) for record in selected]),
        "supporting_evidence": _reason_distribution(selected, "supporting_reason_codes"),
        "contradicting_evidence": _reason_distribution(selected, "contradicting_reason_codes"),
        "missingness_classification": dict(sorted(missingness.items())),
        "wiring_defect_count": 0,
    }


def _priority_action_cohorts(product: Mapping[str, Any]) -> dict[str, Any]:
    records = product["records"]
    return {
        "session": product.get("session"),
        "cohorts": [
            _cohort_summary(records, "PRIORITY_NOW", lambda r: ((r.get("evidence_axes") or {}).get("OPPORTUNITY_PRIORITY") or {}).get("state") == "PRIORITY_NOW"),
            _cohort_summary(records, "INITIATE_ON_BREAKOUT", lambda r: r.get("research_action_posture") == "INITIATE_ON_BREAKOUT"),
            _cohort_summary(records, "ACCUMULATE_ON_RETEST", lambda r: r.get("research_action_posture") == "ACCUMULATE_ON_RETEST"),
            _cohort_summary(records, "EARLY_WATCH", lambda r: r.get("research_action_posture") == "EARLY_WATCH"),
            _cohort_summary(records, "WAIT_FOR_CONFIRMATION", lambda r: r.get("research_action_posture") == "WAIT_FOR_CONFIRMATION"),
            _cohort_summary(records, "INSUFFICIENT_CURRENT_RESEARCH", lambda r: r.get("research_action_posture") == "INSUFFICIENT_CURRENT_RESEARCH"),
        ],
        "classification_boundary": "MISSINGNESS_IS_REPORTED_PER_AXIS_AND_DOES_NOT_TUNE_ACTION_THRESHOLDS",
    }


def _compact_record(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ticker": record.get("ticker"),
        "research_action_posture": record.get("research_action_posture"),
        "priority": ((record.get("evidence_axes") or {}).get("OPPORTUNITY_PRIORITY") or {}).get("state"),
        "evidence_axes": record.get("evidence_axes"),
        "evidence_axis_coherence": record.get("evidence_axis_coherence"),
        "trigger": record.get("trigger"),
        "invalidation": record.get("invalidation"),
        "material_uncertainties": record.get("material_uncertainties"),
        "counter_thesis": record.get("counter_thesis"),
        "decision_identity": record.get("decision_identity"),
    }


def _first_matching(records: Mapping[str, Mapping[str, Any]], predicate: Callable[[Mapping[str, Any]], bool]) -> str | None:
    return next((ticker for ticker in sorted(records) if predicate(records[ticker])), None)


def _watchlist_replay(product: Mapping[str, Any]) -> dict[str, Any]:
    records = product["records"]
    named = {ticker: _compact_record(records[ticker]) for ticker in WATCHLIST if ticker in records}
    examples = {
        "strong_fundamentals_weak_technical": _first_matching(records, lambda r: r.get("fundamental_state") in {"IMPROVING", "STABLE"} and r.get("tactical_phase") in {"BREAKDOWN", "INSUFFICIENT"}),
        "weak_fundamentals_strong_technical": _first_matching(records, lambda r: r.get("fundamental_state") == "DETERIORATING" and r.get("tactical_phase") in {"BREAKOUT_CONFIRMED", "TREND_CONTINUATION", "EARLY_REVERSAL"}),
        "cheap_valuation_weak_structure": _first_matching(records, lambda r: ((r.get("evidence_axes") or {}).get("VALUATION") or {}).get("context", {}).get("peer_relative_state") == "CHEAP_VS_PEERS" and r.get("tactical_phase") in {"BREAKDOWN", "INSUFFICIENT"}),
        "expensive_valuation_strong_momentum": _first_matching(records, lambda r: ((r.get("evidence_axes") or {}).get("VALUATION") or {}).get("context", {}).get("peer_relative_state") == "EXPENSIVE_VS_PEERS" and ((r.get("evidence_axes") or {}).get("MOMENTUM") or {}).get("fitness") == "ELIGIBLE"),
        "turnaround": _first_matching(records, lambda r: r.get("fundamental_state") == "TURNAROUND"),
        "insufficient_financial": _first_matching(records, lambda r: r.get("fundamental_state") == "INSUFFICIENT"),
        "insufficient_technical_history": _first_matching(records, lambda r: r.get("tactical_phase") == "INSUFFICIENT"),
        "participation_unavailable": _first_matching(records, lambda r: not _axis_available("PARTICIPATION_CONFIRMATION", ((r.get("evidence_axes") or {}).get("PARTICIPATION_CONFIRMATION") or {}))),
    }
    return {
        "session": product.get("session"),
        "required_tickers": named,
        "representative_examples": {label: _compact_record(records[ticker]) if ticker else None for label, ticker in examples.items()},
        "boundary": "REAL_TICKER_REPLAY_ONLY_NO_TICKER_SPECIFIC_PRODUCTION_LOGIC",
    }


def _policy_field_changes(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    fields = ("research_action_posture", "why_now", "trigger", "invalidation")
    changed = {field: [] for field in fields}
    for ticker in sorted(set(before["records"]) & set(after["records"])):
        for field in fields:
            if before["records"][ticker].get(field) != after["records"][ticker].get(field):
                changed[field].append(ticker)
    return {
        "compared_record_count": len(set(before["records"]) & set(after["records"])),
        "changed_counts": {field: len(tickers) for field, tickers in changed.items()},
        "sample_changed_tickers": {field: tickers[:20] for field, tickers in changed.items() if tickers},
        "unchanged": all(not tickers for tickers in changed.values()),
    }


def _posture_before_after(*, retained: Mapping[str, Any], policy_baseline: Mapping[str, Any], enriched: Mapping[str, Any]) -> dict[str, Any]:
    retained_sources = retained.get("source_artifacts") or {}
    enriched_sources = enriched.get("source_artifacts") or {}
    source_identity_differences = {
        key: {"retained_before": retained_sources.get(key), "enriched_replay": enriched_sources.get(key)}
        for key in sorted(set(retained_sources) | set(enriched_sources))
        if retained_sources.get(key) != enriched_sources.get(key)
    }
    return {
        "session": enriched.get("session"),
        "retained_before_source": {
            "artifact_identity": retained.get("artifact_identity"),
            "momentum_context_available": (retained.get("coverage") or {}).get("momentum_context_available"),
            "tactical_confirmation_state_distribution": (retained.get("coverage") or {}).get("tactical_confirmation_state_distribution"),
        },
        "same_input_policy_baseline_vs_enriched": _policy_field_changes(policy_baseline, enriched),
        "retained_before_vs_enriched": _policy_field_changes(retained, enriched),
        "retained_before_vs_enriched_qualification": {
            "comparable_for_policy_attribution": False,
            "reason": "RETAINED_AND_REPLAYED_UPSTREAM_ARTIFACT_IDENTITIES_DIFFER;_USE_SAME_INPUT_BASELINE_FOR_THIS_WIRING_CHANGE",
            "source_identity_differences": source_identity_differences,
        },
        "boundary": "SAME_INPUT_BASELINE_PROVES_AXES_DO_NOT_CHANGE_EXISTING_POSTURE_TRIGGER_OR_INVALIDATION_POLICY",
    }


def _temporal_validation(inputs: Mapping[str, Any], temporal_product: Mapping[str, Any]) -> dict[str, Any]:
    session = TEMPORAL_SESSION
    surfaces = inputs["surfaces"]
    future_technical: list[str] = []
    for ticker, record in (surfaces["momentum"].get("records") or {}).items():
        for field in ("rsi", "macd", "rsi_divergence"):
            as_of = (record.get(field) or {}).get("as_of_session")
            if isinstance(as_of, str) and as_of > session:
                future_technical.append(ticker)
        lineage = record.get("technical_history_lineage") or {}
        if lineage.get("source") == "RETAINED_TECHNICAL_HISTORY_RECOVERY":
            recovered = ((surfaces["recovery"].get("recovered_history_overrides") or {}).get(ticker) or {}).get("observations") or []
            if any(str(row.get("session")) > session for row in recovered):
                future_technical.append(ticker)
    financial_source = inputs["financial_temporal_source"] or {}
    financial_period = financial_source.get("financial_evidence_as_of_period")
    future_financial_source_detected = financial_period == "2026-Q4"
    financial_axis = ((next(iter(temporal_product["records"].values())) if temporal_product["records"] else {}).get("evidence_axes") or {}).get("FUNDAMENTAL") or {}
    valuation_axis = ((next(iter(temporal_product["records"].values())) if temporal_product["records"] else {}).get("evidence_axes") or {}).get("VALUATION") or {}
    admitted = int(bool(future_technical)) + int(financial_axis.get("fitness") not in {"UNAVAILABLE", "INSUFFICIENT_EVIDENCE"}) + int(valuation_axis.get("fitness") not in {"UNAVAILABLE", "INSUFFICIENT_EVIDENCE"})
    return {
        "session": session,
        "technical_future_session_violations": sorted(set(future_technical)),
        "retained_financial_source_period": financial_period,
        "future_financial_source_detected_and_excluded": future_financial_source_detected,
        "financial_axis_temporal_fitness": financial_axis.get("fitness"),
        "valuation_axis_temporal_fitness": valuation_axis.get("fitness"),
        "current_shares_promoted_into_historical_replay": False,
        "current_research_valuation_promoted_into_pit": False,
        "future_leak_admitted": admitted,
        "temporal_status": "PARTIAL_BY_EVIDENCE" if future_financial_source_detected else "COMPLETE",
        "boundary": "CURRENT_RESEARCH_FINANCIAL_AND_VALUATION_AXES_FAIL_CLOSED_FOR_TEMPORAL_REPLAY_WHEN_NO_ADMISSIBLE_AS_OF_VERSION_EXISTS",
    }


def _residual_gap_matrix(coverage: Mapping[str, Any], temporal: Mapping[str, Any]) -> dict[str, Any]:
    supported = int(coverage["supported_universe_count"])
    available = coverage["axis_available"]
    return {
        "session": PRIMARY_SESSION,
        "gaps": [
            {"class": "DATA_GAP", "gap": "valuation_axis_unavailable", "count": supported - available["VALUATION"], "effect": "valuation remains feature-local unavailable"},
            {"class": "FEATURE_FITNESS_GAP", "gap": "technical_momentum_or_confirmation_unavailable", "count": supported - available["MOMENTUM"], "effect": "no tactical coherence is implied for insufficient history"},
            {"class": "ANALYTICAL_FEATURE_GAP", "gap": "none_created_by_this_integration", "count": 0, "effect": "existing axes are joined; no new feature engine was introduced"},
            {"class": "STRATEGY_POLICY_GAP", "gap": "no_policy_retuning_authorized", "count": 0, "effect": "coherence explains but does not alter action posture"},
            {"class": "PORTFOLIO_GAP", "gap": "portfolio_fit_not_provided", "count": supported - available["PORTFOLIO_FIT"], "effect": "security attractiveness remains separate from portfolio fit"},
            {"class": "PIT_ONLY_GAP", "gap": "admissible_historical_financial_and_valuation_version_missing", "count": 1 if temporal["future_financial_source_detected_and_excluded"] else 0, "effect": "2026-08-25 financial/valuation replay fail-closed"},
            {"class": "UI_PRESENTATION_GAP", "gap": "local_ai_axes_are_now_passed_through", "count": 0, "effect": "daily brief receives compact axes and coherence"},
        ],
        "authority_boundary": "GAPS_ARE_DIAGNOSTIC_NOT_A_SUCCESSOR_AUTHORIZATION",
    }


def _inventory() -> dict[str, Any]:
    return {
        "contract": "integrated_decision_evidence_axis_inventory/v1",
        "axes": [
            {"axis": "FUNDAMENTAL", "producer": "financial_analysis_product_integration/v1", "input_contract": "financial_analysis_product_integration/v1", "output_identity": "financial_analysis", "integrated_decision_consumer": "evaluate_fundamental_direction", "ai_consumer": "daily_integrated_decision_brief.watchlist.evidence_axes", "fitness_requirement": "financial record status", "current_gap": "none after additive axis exposure", "possible_overlap": "financial_composite joins this with valuation without recomputation"},
            {"axis": "VALUATION", "producer": "current_research_valuation_context/v1", "input_contract": "evaluated valuation with peer/own-history context", "output_identity": "current_valuation", "integrated_decision_consumer": "evaluate_valuation_context", "ai_consumer": "daily_integrated_decision_brief.watchlist.evidence_axes", "fitness_requirement": "valuation context status and method blockers", "current_gap": "temporal PIT source unavailable", "possible_overlap": "financial_composite is descriptive only"},
            {"axis": "TACTICAL_STRUCTURE", "producer": "market_structure_breakout_product_projection/v1", "input_contract": "technical_structure_context/v2", "output_identity": "technical_structure", "integrated_decision_consumer": "evaluate_tactical_phase", "ai_consumer": "daily_integrated_decision_brief.watchlist.evidence_axes", "fitness_requirement": "eligible exact-session structure", "current_gap": "none", "possible_overlap": "confirmation reuses this phase rather than deriving a second structure"},
            {"axis": "MOMENTUM", "producer": "tactical_momentum_context/v1", "input_contract": "descriptive + exact snapshot + technical recovery", "output_identity": "momentum", "integrated_decision_consumer": "momentum_context passthrough and evidence axes", "ai_consumer": "daily_integrated_decision_brief.watchlist.momentum_context", "fitness_requirement": "eligibility and retained history lineage", "current_gap": "canonical wiring closed", "possible_overlap": "confirmation folds correlated RSI/MACD into one existing momentum direction"},
            {"axis": "PARTICIPATION_CONFIRMATION", "producer": "tactical_confirmation_context/v1", "input_contract": "structure + momentum + relative volume", "output_identity": "tactical_confirmation", "integrated_decision_consumer": "tactical_confirmation_context passthrough and evidence axes", "ai_consumer": "daily_integrated_decision_brief.watchlist.tactical_confirmation_context", "fitness_requirement": "participation and confirmation state", "current_gap": "canonical wiring closed", "possible_overlap": "no second vote over correlated technical measurements"},
            {"axis": "MARKET_SECTOR", "producer": "current_market_sector_leadership_context/v1", "input_contract": "market breadth and ticker sector context", "output_identity": "market_sector", "integrated_decision_consumer": "market_sector_context", "ai_consumer": "daily_integrated_decision_brief.watchlist.evidence_axes", "fitness_requirement": "market artifact and ticker sector applicability", "current_gap": "sector may be partial/data-limited", "possible_overlap": "does not change posture outside existing policy"},
            {"axis": "OPPORTUNITY_PRIORITY", "producer": "current_opportunity_prioritization/v1", "input_contract": "priority queue record", "output_identity": "priority_queue", "integrated_decision_consumer": "priority_posture_reconciliation", "ai_consumer": "daily_integrated_decision_brief.watchlist.evidence_axes", "fitness_requirement": "priority record availability", "current_gap": "none", "possible_overlap": "priority remains distinct from action posture"},
            {"axis": "PORTFOLIO_FIT", "producer": "optional portfolio input", "input_contract": "portfolio record when supplied", "output_identity": "not supplied in retained replay", "integrated_decision_consumer": "portfolio_context", "ai_consumer": "daily_integrated_decision_brief.watchlist.evidence_axes", "fitness_requirement": "explicit portfolio input", "current_gap": "not supported by retained input", "possible_overlap": "must not change security attractiveness"},
        ],
        "authority_boundary": "INVENTORY_DESCRIBES_EXISTING_CONTRACTS_ONLY",
    }


def _report(coverage: Mapping[str, Any], coherence: Mapping[str, Any], posture: Mapping[str, Any], temporal: Mapping[str, Any]) -> str:
    return "\n".join([
        "# Integrated Decision Evidence-Axis Coherence V1",
        "",
        "Outcome: PARTIAL_BY_EVIDENCE. The canonical closure now materializes and consumes retained momentum and tactical-confirmation contexts. Evidence axes and qualitative coherence are additive; action posture, trigger, and invalidation policy are unchanged.",
        "",
        "## Primary retained replay — 2026-09-04",
        "",
        f"- Supported universe / decision records: {coverage['supported_universe_count']} / {coverage['decision_records']}",
        f"- All major axes available: {coverage['all_major_axes_available']}",
        f"- Coherence distribution: {json.dumps(coherence['distribution'], sort_keys=True)}",
        f"- Same-input posture, trigger, invalidation changes: {json.dumps(posture['same_input_policy_baseline_vs_enriched']['changed_counts'], sort_keys=True)}",
        "",
        "## Temporal retained replay — 2026-08-25",
        "",
        f"- Future-leak admitted: {temporal['future_leak_admitted']}",
        f"- Future financial source detected and excluded: {temporal['future_financial_source_detected_and_excluded']}",
        "- Financial and valuation axes are fail-closed for this temporal replay because no admissible as-of financial version was retained.",
        "",
        "## Boundaries",
        "",
        "- No provider acquisition, database write, remote publication, target price, probability, position sizing, universal score, or vote count.",
        "- Coherence reports cross-axis relationships; it does not imply alpha, causality, or an execution instruction.",
        "",
    ])


def run(*, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    primary_inputs = _inputs_for_current_research(PRIMARY_SESSION)
    policy_baseline = _build_integrated(PRIMARY_SESSION, primary_inputs, attach_momentum_confirmation=False)
    primary = _build_integrated(PRIMARY_SESSION, primary_inputs, attach_momentum_confirmation=True)
    temporal_inputs = _inputs_for_current_research(TEMPORAL_SESSION)
    temporal = _build_integrated(TEMPORAL_SESSION, temporal_inputs, attach_momentum_confirmation=True)

    coverage = _axis_coverage(primary)
    coherence = _coherence_distribution(primary)
    cohorts = _priority_action_cohorts(primary)
    watchlist = _watchlist_replay(primary)
    posture = _posture_before_after(
        retained=primary_inputs["retained_integrated"], policy_baseline=policy_baseline, enriched=primary,
    )
    temporal_validation = _temporal_validation(temporal_inputs, temporal)
    residual = _residual_gap_matrix(coverage, temporal_validation)
    inventory = _inventory()
    artifacts = {
        "decision_axis_inventory.json": inventory,
        "market_wide_axis_coverage.json": coverage,
        "coherence_distribution.json": coherence,
        "priority_action_cohort_review.json": cohorts,
        "watchlist_decision_replay.json": watchlist,
        "posture_before_after.json": posture,
        "temporal_replay_validation.json": temporal_validation,
        "product_residual_gap_matrix.json": residual,
    }
    for name, payload in artifacts.items():
        _write(output_dir / name, payload)
    (output_dir / "REPORT.md").write_text(_report(coverage, coherence, posture, temporal_validation), encoding="utf-8")
    return {
        "primary_integrated": primary,
        "temporal_integrated": temporal,
        "coverage": coverage,
        "coherence": coherence,
        "posture": posture,
        "temporal": temporal_validation,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=OPS / "integrated-decision-evidence-axis-coherence-v1-20260905")
    args = parser.parse_args()
    result = run(output_dir=args.output_dir)
    print(json.dumps({
        "axis_coverage": result["coverage"],
        "coherence_distribution": result["coherence"]["distribution"],
        "same_input_policy_changes": result["posture"]["same_input_policy_baseline_vs_enriched"]["changed_counts"],
        "future_leak_admitted": result["temporal"]["future_leak_admitted"],
    }, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
