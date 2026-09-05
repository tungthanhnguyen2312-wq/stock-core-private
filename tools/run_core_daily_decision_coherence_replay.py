"""Local-only retained replay for CORE_DAILY_DECISION_COHERENCE_AND_VALUATION_INTEGRATION_V1.

This runner never acquires market data, writes a database, invokes a Daily publisher, or
changes a registered session input.  It rebuilds the current-research consumer surfaces from
the immutable 2026-09-04 inputs into an explicitly named operations-review directory.
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
WATCHLIST = ("EVF", "FPT", "HPG", "NVL", "PAN", "PNJ", "POW", "PVD", "QNS", "SSI", "VNM")
VALIDATION_TICKERS = ("QNS", "FPT", "HPG", "STB", "LPB")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _identity(payload: Mapping[str, Any]) -> str:
    stable = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "core_daily_decision_coherence_reconciliation:" + hashlib.sha256(stable.encode("utf-8")).hexdigest()


def _priority_queue(session: str) -> dict[str, Any]:
    candidates = sorted((OPS / "daily-research-session-operations-v1" / session).glob("*/daily_opportunity_decision_queue_artifact.json"))
    if not candidates:
        raise ValueError("RETAINED_PRIORITY_QUEUE_NOT_FOUND")
    values = [_load(path) for path in candidates]
    identities = {value.get("artifact_identity") for value in values}
    if len(identities) != 1:
        raise ValueError("RETAINED_PRIORITY_QUEUE_IDENTITY_AMBIGUOUS")
    return values[0]


def _cross_tab(queue: Mapping[str, Any], integrated: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    rows: Counter[tuple[str, str]] = Counter()
    for ticker, queue_record in (queue.get("records") or {}).items():
        posture = ((integrated.get("records") or {}).get(ticker) or {}).get("research_action_posture", "MISSING_INTEGRATED")
        rows[(str(queue_record.get("research_priority_tier")), str(posture))] += 1
    output: dict[str, dict[str, int]] = {}
    for (tier, posture), count in sorted(rows.items()):
        output.setdefault(tier, {})[posture] = count
    return output


def _watchlist_view(integrated: Mapping[str, Any], raw_valuation: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for ticker in WATCHLIST:
        decision = ((integrated.get("records") or {}).get(ticker) or {})
        raw = ((raw_valuation.get("records") or {}).get(ticker) or {})
        raw_methods = raw.get("metrics") or {}
        methods = decision.get("valuation_methods") or {}
        readiness = (decision.get("calculation_readiness_context") or {}).get("calculation_readiness") or []
        result[ticker] = {
            "research_action_posture": decision.get("research_action_posture"),
            "tactical_phase": decision.get("tactical_phase"),
            "trigger": decision.get("trigger"),
            "invalidation": decision.get("invalidation"),
            "priority_posture_reconciliation": decision.get("priority_posture_reconciliation"),
            "raw_price_input": raw.get("price_input"),
            "raw_valuation_methods": {
                name: {key: (raw_methods.get(name) or {}).get(key) for key in ("status", "value", "blocked_reasons", "financial_period", "monetary_compatibility")}
                for name in ("P/E", "P/B", "P/S", "EV/Sales", "EV/EBITDA", "market_cap")
            },
            "current_research_methods": methods,
            "calculation_readiness": readiness,
            "method_reconciliation": decision.get("valuation_method_reconciliation"),
        }
    return result


def _regression_projection_check() -> dict[str, Any]:
    """Assert the recovered-history consumer produces the already-retained 2026-08-25 projection."""
    import market_structure_breakout_product_projection as projection
    import technical_structure_context as structure

    session = "2026-08-25"
    token = session.replace("-", "")
    descriptive = _load(OPS / f"market-wide-current-descriptive-research-v1-{token}" / "market_wide_current_descriptive_research_artifact.json")
    snapshot = _load(OPS / f"p3f9b-market-wide-exact-session-scaleout-{token}" / "p3f9b_mva_exact_session_snapshot.json")
    recovery = _load(OPS / f"market-wide-current-technical-coverage-scaleout-v1-{token}" / "market_wide_current_technical_coverage_recovery_artifact.json")
    retained = _load(OPS / "integrated-investment-decision-product-v1-20260825" / "market_structure_breakout_v3_projection_artifact.json")
    rebuilt = projection.build_artifact(
        technical_structure=structure.build_artifact(
            current_descriptive=descriptive, p3f9b_snapshot=snapshot,
            technical_history_recovery_artifact=recovery, requested_at="2026-09-05T00:00:00+07:00",
        ),
        requested_at="2026-09-05T00:00:00+07:00",
    )
    fields = ("eligible", "close_history_depth", "market_structure_state", "breakout_state_v3", "trigger_type", "trigger_state", "invalidation_level")
    differences = [
        ticker for ticker in rebuilt["records"]
        if {field: rebuilt["records"][ticker].get(field) for field in fields}
        != {field: (retained.get("records", {}).get(ticker) or {}).get(field) for field in fields}
    ]
    integrated = _load(OPS / "integrated-investment-decision-product-v1-20260825" / "integrated_investment_decision_product_artifact.json")
    return {
        "session": session,
        "retained_integrated_posture_distribution": integrated.get("coverage", {}).get("research_action_posture_distribution"),
        "replayed_tactical_projection_coverage": rebuilt.get("coverage"),
        "comparable_tactical_field_difference_count": len(differences),
        "preserves_previously_valid_tactical_states": not differences,
    }


def run(*, runtime_root: Path, output_dir: Path, session: str = PRIMARY_SESSION) -> dict[str, Any]:
    if session != PRIMARY_SESSION:
        raise ValueError("THIS_RETAINED_REPLAY_IS_PINNED_TO_2026-09-04")
    import canonical_daily_financial_v2_materialization as financial_materialization
    import financial_v2_current_input_authority as financial_authority
    import integrated_investment_decision_product as integrated_product
    import market_structure_breakout_product_projection as projection
    import market_wide_relative_volume_research as relative_volume
    import technical_structure_context as structure
    from tools.derive_market_wide_current_valuation_input_scaleout import materialize

    output_dir.mkdir(parents=True, exist_ok=True)
    token = session.replace("-", "")
    snapshot_path = OPS / f"p3f9b-market-wide-exact-session-scaleout-{token}" / "p3f9b_mva_exact_session_snapshot.json"
    snapshot = _load(snapshot_path)
    descriptive = _load(OPS / f"market-wide-current-descriptive-research-v1-{token}" / "market_wide_current_descriptive_research_artifact.json")
    recovery = _load(OPS / f"market-wide-current-technical-coverage-scaleout-v1-{token}" / "market_wide_current_technical_coverage_recovery_artifact.json")
    sector = _load(OPS / f"current-market-sector-leadership-context-v1-{token}" / "current_market_sector_leadership_context_artifact.json")
    opportunity = _load(OPS / f"current-opportunity-prioritization-v1-{token}" / "current_opportunity_prioritization_artifact.json")
    queue = _priority_queue(session)
    requested_at = "2026-09-05T00:00:00+07:00"

    raw_path = output_dir / "primary_20260904_raw_valuation_artifact.json"
    raw = materialize(
        raw_path, runtime_root=runtime_root, price=snapshot_path, expected_session=session,
        report=output_dir / "primary_20260904_raw_valuation_report.json",
    )
    technical = structure.build_artifact(
        current_descriptive=descriptive, p3f9b_snapshot=snapshot,
        technical_history_recovery_artifact=recovery, requested_at=requested_at,
    )
    tactical = projection.build_artifact(technical_structure=technical, requested_at=requested_at)
    tickers = sorted(snapshot.get("records") or {})
    relative = relative_volume.build_artifact(
        candidates=tickers, records=snapshot.get("records") or {}, session=session, requested_at=requested_at,
    )
    authority = financial_authority.resolve(ROOT)
    engine = financial_materialization.build_engine_artifact(root=ROOT, requested_at=requested_at, authority=authority)
    financial = financial_materialization.build_session_artifact(
        root=ROOT, decision_session=session, product_tickers=tickers, requested_at=requested_at,
        authority=authority, engine_artifact=engine,
    )
    readiness = financial_materialization.build_calculation_readiness_context(
        runtime_root=runtime_root, decision_session=session, raw_valuation_artifact=raw,
        product_tickers=tickers, requested_at=requested_at,
    )
    valuation = financial_materialization.build_evaluated_valuation_artifact(
        engine_artifact=engine, raw_valuation_artifact=raw, product_tickers=tickers,
        requested_at=requested_at, calculation_readiness_context=readiness,
    )
    integrated = integrated_product.build_artifact(
        session=session, requested_at=requested_at, technical_structure_artifact=tactical,
        financial_analysis_artifact=financial["financial_analysis_product"],
        current_valuation_artifact=valuation, relative_volume_artifact=relative,
        market_sector_artifact=sector, legacy_decision_artifact=opportunity,
        priority_queue_artifact=queue,
    )
    artifacts = {
        "primary_20260904_technical_structure_artifact.json": technical,
        "primary_20260904_tactical_projection_artifact.json": tactical,
        "primary_20260904_relative_volume_artifact.json": relative,
        "primary_20260904_financial_analysis_product_artifact.json": financial,
        "primary_20260904_calculation_readiness_context_artifact.json": readiness,
        "primary_20260904_current_research_valuation_context_artifact.json": valuation,
        "primary_20260904_integrated_investment_decision_product_artifact.json": integrated,
    }
    for name, artifact in artifacts.items():
        _write(output_dir / name, artifact)

    priority_relevant = [
        ticker for ticker, record in (queue.get("records") or {}).items()
        if record.get("research_priority_tier") == "PRIORITY_NOW" and record.get("entry_relevant") is True
    ]
    reconciliation_categories = Counter(
        ((integrated.get("records") or {}).get(ticker) or {}).get("priority_posture_reconciliation", {}).get("reconciliation_category", "MISSING")
        for ticker in priority_relevant
    )
    method_reconciliation = Counter(
        item.get("comparison_status", "MISSING")
        for row in (valuation.get("records") or {}).values()
        for item in (row.get("valuation_method_reconciliation") or {}).values()
    )
    report: dict[str, Any] = {
        "artifact_type": "CORE_DAILY_DECISION_COHERENCE_RECONCILIATION",
        "contract_version": "core_daily_decision_coherence_reconciliation/v1",
        "session": session,
        "source_artifacts": {
            "exact_session_snapshot": snapshot.get("snapshot_identity"),
            "technical_history_recovery": recovery.get("artifact_identity"),
            "priority_queue": queue.get("artifact_identity"),
            "raw_valuation": raw.get("artifact_identity"),
            "integrated_decision": integrated.get("artifact_identity"),
        },
        "lineage_finding": {
            "classification_before_corrective": ["MISSING_HISTORY_OR_FEATURE_FITNESS", "PROJECTION_LOSS"],
            "root_cause": "Technical features consumed recovered history while technical_structure_context consumed one-bar exact-session records.",
            "corrective": "technical_structure_context now verifies and consumes matching RECOVERED_COMPLETE_TECHNICAL_HISTORY overrides.",
            "policy_thresholds_changed": False,
        },
        "technical": {
            "universe_denominator": len(tickers),
            "technical_history_complete_count": len(recovery.get("recovered_history_overrides") or {}),
            "technical_structure_coverage": technical.get("coverage"),
            "tactical_projection_coverage": tactical.get("coverage"),
        },
        "queue": {
            "entry_relevant_summary": queue.get("entry_relevant_summary"),
            "priority_by_integrated_posture": _cross_tab(queue, integrated),
            "priority_now_entry_relevant_count": len(priority_relevant),
            "priority_now_entry_relevant_reconciliation_categories": dict(sorted(reconciliation_categories.items())),
            "all_priority_now_entry_relevant_have_explanation": all(
                ((integrated.get("records") or {}).get(ticker) or {}).get("priority_posture_reconciliation")
                for ticker in priority_relevant
            ),
        },
        "integrated": integrated.get("coverage"),
        "valuation": {
            "raw_valuation_coverage": raw.get("coverage"),
            "calculation_readiness_coverage": readiness.get("coverage"),
            "comparable_lane_reconciliation_counts": dict(sorted(method_reconciliation.items())),
            "unit_defect_outcomes": {
                "price_representation_contract": "DNSE:ohlc_1D:VN_LISTED_EQUITY:kvnd_to_vnd/v1",
                "cross_currency_multiples": "BLOCKED_WITHOUT_FX_CONVERSION_CONTRACT",
                "unresolved_noncanonical_financial_value_scale": "BLOCKED_WITHOUT_GUESSING_A_SCALE",
            },
        },
        "watchlist": _watchlist_view(integrated, raw),
        "required_validation_tickers": {
            ticker: ((integrated.get("records") or {}).get(ticker) or {}).get("priority_posture_reconciliation")
            for ticker in VALIDATION_TICKERS
        },
        "regression_20260825": _regression_projection_check(),
        "authority_boundary": {
            "no_network": True,
            "no_publish": True,
            "no_database_write": True,
            "no_raw_as_traded_pit_liquidity_sizing_execution_promotion": True,
            "no_score_target_price_probability": True,
        },
    }
    report["artifact_identity"] = _identity(report)
    _write(output_dir / "primary_20260904_reconciliation_artifact.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=OPS / "core-daily-decision-coherence-and-valuation-integration-v1-20260905")
    parser.add_argument("--session", default=PRIMARY_SESSION)
    args = parser.parse_args()
    report = run(runtime_root=args.runtime_root, output_dir=args.output_dir, session=args.session)
    print(json.dumps({
        "artifact_identity": report["artifact_identity"], "session": report["session"],
        "integrated": report["integrated"], "queue": report["queue"],
        "regression_20260825": report["regression_20260825"],
    }, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
