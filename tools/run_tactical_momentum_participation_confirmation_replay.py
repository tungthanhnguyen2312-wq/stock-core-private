"""Local-only retained replay for TACTICAL_MOMENTUM_PARTICIPATION_CONFIRMATION_V1.

This runner never acquires market data, writes a database, invokes a Daily publisher, or changes
a registered session input. It rebuilds the current-research structure/momentum/participation/
confirmation/integrated surfaces from the immutable 2026-09-04 inputs, reusing the already-correct
retained financial and valuation artifacts from CORE_DAILY_DECISION_COHERENCE_AND_VALUATION_
INTEGRATION_V1 verbatim (valuation semantics are unchanged by this milestone; recomputing them
here would risk re-deriving what is already retained evidence).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
OPS = ROOT / "operations-review"
PRIMARY_SESSION = "2026-09-04"
REGRESSION_SESSION = "2026-08-25"
VALIDATION_TICKERS = ("QNS", "FPT", "HPG", "STB", "LPB", "PNJ", "SSI", "PVD")
PRIOR_MILESTONE_DIR = OPS / "core-daily-decision-coherence-and-valuation-integration-v1-20260905"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _identity(payload: Mapping[str, Any]) -> str:
    stable = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "tactical_momentum_participation_confirmation_reconciliation:" + hashlib.sha256(stable.encode("utf-8")).hexdigest()


def _priority_queue(session: str) -> dict[str, Any]:
    candidates = sorted((OPS / "daily-research-session-operations-v1" / session).glob("*/daily_opportunity_decision_queue_artifact.json"))
    if not candidates:
        raise ValueError("RETAINED_PRIORITY_QUEUE_NOT_FOUND")
    values = [_load(path) for path in candidates]
    identities = {value.get("artifact_identity") for value in values}
    if len(identities) != 1:
        raise ValueError("RETAINED_PRIORITY_QUEUE_IDENTITY_AMBIGUOUS")
    return values[0]


def _build_current_research_surfaces(session: str) -> dict[str, Any]:
    """Build structure/momentum/participation/confirmation from retained inputs for one session."""
    import market_structure_breakout_product_projection as projection
    import market_wide_relative_volume_research as relative_volume
    import tactical_confirmation_context as confirmation
    import tactical_momentum_context as momentum
    import technical_structure_context as structure

    token = session.replace("-", "")
    requested_at = "2026-09-05T00:00:00+07:00"
    snapshot = _load(OPS / f"p3f9b-market-wide-exact-session-scaleout-{token}" / "p3f9b_mva_exact_session_snapshot.json")
    descriptive = _load(OPS / f"market-wide-current-descriptive-research-v1-{token}" / "market_wide_current_descriptive_research_artifact.json")
    recovery = _load(OPS / f"market-wide-current-technical-coverage-scaleout-v1-{token}" / "market_wide_current_technical_coverage_recovery_artifact.json")
    tickers = sorted(snapshot.get("records") or {})

    technical = structure.build_artifact(
        current_descriptive=descriptive, p3f9b_snapshot=snapshot,
        technical_history_recovery_artifact=recovery, requested_at=requested_at,
    )
    tactical = projection.build_artifact(technical_structure=technical, requested_at=requested_at)
    momentum_artifact = momentum.build_artifact(
        current_descriptive=descriptive, p3f9b_snapshot=snapshot,
        technical_history_recovery_artifact=recovery, requested_at=requested_at,
    )
    participation_records = relative_volume.resolve_records_with_recovery(
        p3f9b_snapshot=snapshot, technical_history_recovery_artifact=recovery,
        candidates=tickers, target_session=session,
    )
    participation_artifact = relative_volume.build_artifact(
        candidates=tickers, records=participation_records, session=session, requested_at=requested_at,
    )
    confirmation_artifact = confirmation.build_artifact(
        structure_projection=tactical, momentum=momentum_artifact, participation=participation_artifact,
        requested_at=requested_at,
    )
    return {
        "snapshot": snapshot, "descriptive": descriptive, "recovery": recovery, "tickers": tickers,
        "technical": technical, "tactical": tactical, "momentum": momentum_artifact,
        "participation": participation_artifact, "confirmation": confirmation_artifact,
    }


def _cross_tab(records: Mapping[str, Mapping[str, Any]], key_a: str, key_b: str) -> dict[str, dict[str, int]]:
    rows: Counter[tuple[str, str]] = Counter()
    for record in records.values():
        rows[(str(record.get(key_a)), str(record.get(key_b)))] += 1
    output: dict[str, dict[str, int]] = {}
    for (a, b), count in sorted(rows.items()):
        output.setdefault(a, {})[b] = count
    return output


def _named_diagnostics(integrated_records: Mapping[str, Any]) -> dict[str, Any]:
    result = {}
    for ticker in VALIDATION_TICKERS:
        record = integrated_records.get(ticker) or {}
        momentum_ctx = record.get("momentum_context") or {}
        result[ticker] = {
            "research_action_posture": record.get("research_action_posture"),
            "tactical_phase": record.get("tactical_phase"),
            "structure_stance": (record.get("tactical_confirmation_context") or {}).get("structure_stance"),
            "tactical_confirmation_state": (record.get("tactical_confirmation_context") or {}).get("tactical_confirmation_state"),
            "supporting_reasons": (record.get("tactical_confirmation_context") or {}).get("supporting_reasons"),
            "contradicting_reasons": (record.get("tactical_confirmation_context") or {}).get("contradicting_reasons"),
            "rsi": (momentum_ctx.get("rsi") or {}).get("value"),
            "rsi_zone": (momentum_ctx.get("rsi") or {}).get("zone"),
            "macd_sign": (momentum_ctx.get("macd") or {}).get("sign"),
            "macd_cross_event": (momentum_ctx.get("macd") or {}).get("cross_event"),
            "divergence_state": (momentum_ctx.get("rsi_divergence") or {}).get("divergence_state"),
            "ma_ordering": (momentum_ctx.get("moving_average_ordering") or {}).get("ma_ordering"),
        }
    return result


def _bounded_phase_examples(integrated_records: Mapping[str, Any], *, phase_field: str, per_phase: int = 2) -> dict[str, list[str]]:
    """A small, deterministic (sorted-ticker) sample per requested phase, for manual inspection."""
    by_phase: dict[str, list[str]] = {}
    for ticker in sorted(integrated_records):
        phase = integrated_records[ticker].get(phase_field)
        if phase is None:
            continue
        by_phase.setdefault(phase, [])
        if len(by_phase[phase]) < per_phase:
            by_phase[phase].append(ticker)
    return by_phase


def _regression_temporal_check() -> dict[str, Any]:
    """Prove RSI/MA/MACD/divergence for an earlier governed session use only observations
    available by that session, and that the exact-session-close compatibility guard still holds
    (technical_history_lineage never reports RETAINED_TECHNICAL_HISTORY_RECOVERY for a mismatched
    close -- reuses the exact same guard technical_structure_context.py already enforces)."""
    surfaces = _build_current_research_surfaces(REGRESSION_SESSION)
    momentum_records = surfaces["momentum"]["records"]
    snapshot_records = surfaces["snapshot"].get("records") or {}
    recovery_overrides = surfaces["recovery"].get("recovered_history_overrides") or {}

    no_lookahead_violations = []
    mismatch_guard_violations = []
    divergence_backdate_violations = []
    for ticker, record in momentum_records.items():
        lineage = record.get("technical_history_lineage") or {}
        if lineage.get("source") == "RETAINED_TECHNICAL_HISTORY_RECOVERY":
            override = recovery_overrides.get(ticker) or {}
            override_obs = [row for row in override.get("observations", []) if row.get("session") == REGRESSION_SESSION]
            snapshot_obs = [row for row in (snapshot_records.get(ticker) or {}).get("observations", []) if row.get("session") == REGRESSION_SESSION]
            if override_obs and snapshot_obs and override_obs[0].get("close") != snapshot_obs[0].get("close"):
                mismatch_guard_violations.append(ticker)
            all_sessions = [row.get("session") for row in override.get("observations", [])]
            if any(s > REGRESSION_SESSION for s in all_sessions):
                no_lookahead_violations.append(ticker)
        divergence = record.get("rsi_divergence") or {}
        if divergence.get("status") == "AVAILABLE" and divergence.get("as_of_session") != REGRESSION_SESSION:
            divergence_backdate_violations.append(ticker)
        for candidate_key in ("bullish_divergence_candidate", "bearish_divergence_candidate"):
            candidate = divergence.get(candidate_key)
            if candidate and candidate["latest_pivot"]["session"] > REGRESSION_SESSION:
                divergence_backdate_violations.append(ticker)

    eligible_count = sum(1 for r in momentum_records.values() if r["eligibility"]["status"] == "ELIGIBLE")
    return {
        "session": REGRESSION_SESSION,
        "candidate_count": len(momentum_records),
        "eligible_count": eligible_count,
        "rsi_available_count": sum(1 for r in momentum_records.values() if r["rsi"]["status"] == "AVAILABLE"),
        "macd_available_count": sum(1 for r in momentum_records.values() if r["macd"]["status"] == "AVAILABLE"),
        "no_lookahead_violations": no_lookahead_violations,
        "recovery_snapshot_mismatch_guard_violations": mismatch_guard_violations,
        "divergence_backdate_violations": divergence_backdate_violations,
        "temporally_clean": not (no_lookahead_violations or mismatch_guard_violations or divergence_backdate_violations),
    }


def run(*, output_dir: Path, session: str = PRIMARY_SESSION) -> dict[str, Any]:
    if session != PRIMARY_SESSION:
        raise ValueError("THIS_RETAINED_REPLAY_IS_PINNED_TO_2026-09-04")
    import integrated_investment_decision_product as integrated_product

    output_dir.mkdir(parents=True, exist_ok=True)
    token = session.replace("-", "")
    requested_at = "2026-09-05T00:00:00+07:00"

    surfaces = _build_current_research_surfaces(session)
    sector = _load(OPS / f"current-market-sector-leadership-context-v1-{token}" / "current_market_sector_leadership_context_artifact.json")
    opportunity = _load(OPS / f"current-opportunity-prioritization-v1-{token}" / "current_opportunity_prioritization_artifact.json")
    queue = _priority_queue(session)

    # Reused verbatim: valuation/financial semantics are unchanged by this milestone.
    financial = _load(PRIOR_MILESTONE_DIR / "primary_20260904_financial_analysis_product_artifact.json")
    valuation = _load(PRIOR_MILESTONE_DIR / "primary_20260904_current_research_valuation_context_artifact.json")
    relative_volume_legacy = _load(PRIOR_MILESTONE_DIR / "primary_20260904_relative_volume_artifact.json")

    integrated = integrated_product.build_artifact(
        session=session, requested_at=requested_at, technical_structure_artifact=surfaces["tactical"],
        financial_analysis_artifact=financial["financial_analysis_product"],
        current_valuation_artifact=valuation, relative_volume_artifact=relative_volume_legacy,
        market_sector_artifact=sector, legacy_decision_artifact=opportunity, priority_queue_artifact=queue,
        momentum_artifact=surfaces["momentum"], tactical_confirmation_artifact=surfaces["confirmation"],
    )

    artifacts = {
        "primary_20260904_technical_structure_artifact.json": surfaces["technical"],
        "primary_20260904_tactical_projection_artifact.json": surfaces["tactical"],
        "primary_20260904_momentum_context_artifact.json": surfaces["momentum"],
        "primary_20260904_participation_artifact.json": surfaces["participation"],
        "primary_20260904_tactical_confirmation_context_artifact.json": surfaces["confirmation"],
        "primary_20260904_integrated_investment_decision_product_artifact.json": integrated,
    }
    for name, artifact in artifacts.items():
        _write(output_dir / name, artifact)

    momentum_records = surfaces["momentum"]["records"]
    integrated_records = integrated["records"]

    report: dict[str, Any] = {
        "artifact_type": "TACTICAL_MOMENTUM_PARTICIPATION_CONFIRMATION_RECONCILIATION",
        "contract_version": "tactical_momentum_participation_confirmation_reconciliation/v1",
        "session": session,
        "source_artifacts": {
            "technical_structure": surfaces["technical"].get("artifact_identity"),
            "momentum": surfaces["momentum"].get("artifact_identity"),
            "participation": surfaces["participation"].get("artifact_identity"),
            "tactical_confirmation": surfaces["confirmation"].get("artifact_identity"),
            "integrated_decision": integrated.get("artifact_identity"),
        },
        "feature_inventory": {
            "eligible_universe": surfaces["momentum"]["coverage"]["eligible_count"],
            "rsi_coverage": surfaces["momentum"]["coverage"]["rsi_available_count"],
            "rsi_divergence_bullish_candidates": surfaces["momentum"]["coverage"]["rsi_divergence_bullish_candidate_count"],
            "rsi_divergence_bearish_candidates": surfaces["momentum"]["coverage"]["rsi_divergence_bearish_candidate_count"],
            "moving_average_coverage": surfaces["momentum"]["coverage"]["moving_average_available_counts"],
            "macd_coverage": surfaces["momentum"]["coverage"]["macd_available_count"],
            "participation_coverage": surfaces["participation"]["coverage"],
            "tactical_confirmation_state_counts": surfaces["confirmation"]["coverage"]["tactical_confirmation_state_counts"],
            "structure_stance_counts": surfaces["confirmation"]["coverage"]["structure_stance_counts"],
        },
        "cross_tabs": {},
        "named_diagnostics": _named_diagnostics(integrated_records),
        "bounded_phase_examples": _bounded_phase_examples(integrated_records, phase_field="tactical_phase"),
        "regression_temporal_check": _regression_temporal_check(),
        "authority_boundary": {
            "no_network": True, "no_publish": True, "no_database_write": True,
            "no_raw_as_traded_pit_liquidity_sizing_execution_promotion": True,
            "no_score_target_price_probability": True, "no_smc_causal_mythology": True,
        },
    }
    priority_tier_by_ticker = {t: row.get("research_priority_tier") for t, row in (queue.get("records") or {}).items() if isinstance(row, Mapping)}
    flattened = {
        t: {
            "tactical_phase": r.get("tactical_phase"),
            "research_action_posture": r.get("research_action_posture"),
            "priority_tier": priority_tier_by_ticker.get(t),
            "confirmation_state": (r.get("tactical_confirmation_context") or {}).get("tactical_confirmation_state"),
        }
        for t, r in integrated_records.items()
    }
    report["cross_tabs"]["tactical_phase_by_confirmation_state"] = _cross_tab(flattened, "tactical_phase", "confirmation_state")
    report["cross_tabs"]["posture_by_confirmation_state"] = _cross_tab(flattened, "research_action_posture", "confirmation_state")
    report["cross_tabs"]["priority_tier_by_confirmation_state"] = _cross_tab(flattened, "priority_tier", "confirmation_state")
    report["artifact_identity"] = _identity(report)
    _write(output_dir / "primary_20260904_reconciliation_artifact.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=OPS / "tactical-momentum-participation-confirmation-v1-20260905")
    parser.add_argument("--session", default=PRIMARY_SESSION)
    args = parser.parse_args()
    report = run(output_dir=args.output_dir, session=args.session)
    print(json.dumps({
        "artifact_identity": report["artifact_identity"], "session": report["session"],
        "feature_inventory": report["feature_inventory"],
        "regression_temporal_check": report["regression_temporal_check"],
    }, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
