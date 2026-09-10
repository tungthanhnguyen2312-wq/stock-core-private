"""Read-only retained-evidence diagnostic for price-basis feature fitness.

The runner selects a governed completed session through the existing immutable input registry,
then reads only its registered Current Research artifacts.  It performs no provider/API call,
does not run Daily, and does not modify the runtime root.  Its optional output is a new
operations-review artifact in this checkout, never a mutation of the retained input evidence.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import daily_producer_pipeline as producer  # noqa: E402
import daily_research_session_operations as session_operations  # noqa: E402
import price_basis_feature_fitness as basis  # noqa: E402
import technical_structure_context  # noqa: E402


REPRESENTATIVE_TICKERS = ("SSI", "PNJ", "PAN")


def _load_registry(runtime_root: Path) -> Mapping[str, Any]:
    return session_operations.load_registry(runtime_root)


def _feature_availability(feature: str, technical_features: Mapping[str, Any]) -> str:
    values = technical_features.get("values") or {}
    source_statuses = technical_features.get("feature_statuses") or {}
    key = {
        basis.MA20: "ma_20",
        basis.MOMENTUM_RETURN: "momentum_20d",
        basis.LOCAL_PRICE_ACTION: "close",
    }.get(feature)
    if key and values.get(key) is not None:
        return str(source_statuses.get(key) or "RETAINED_VALUE")
    return "NOT_RETAINED_IN_SELECTED_CURRENT_ARTIFACT"


def _current_vs_ma20_divergence(technical_features: Mapping[str, Any]) -> float | None:
    values = technical_features.get("values") or {}
    close, ma20 = values.get("close"), values.get("ma_20")
    if not isinstance(close, (int, float)) or not isinstance(ma20, (int, float)) or ma20 == 0:
        return None
    return (float(close) - float(ma20)) / float(ma20)


def _case(
    *, ticker: str, descriptive: Mapping[str, Any], descriptive_identity: str | None,
    corporate_intelligence: Mapping[str, Any], tactical: Mapping[str, Any], session: str,
) -> dict[str, Any]:
    descriptive_record = (descriptive.get("records") or {}).get(ticker)
    corporate_record = (corporate_intelligence.get("records") or {}).get(ticker)
    tactical_record = (tactical.get("records") or {}).get(ticker)
    if not isinstance(descriptive_record, Mapping):
        return {
            "ticker": ticker,
            "status": "RETAINED_CURRENT_RESEARCH_RECORD_ABSENT",
            "reason_codes": ["NO_RETAINED_CURRENT_RESEARCH_RECORD_FOR_TICKER"],
        }
    technical_features = descriptive_record.get("technical_features") or {}
    context = technical_structure_context.price_basis_fitness_context(
        ticker=ticker,
        technical_features=technical_features,
        source_artifact_identity=descriptive_identity,
        provider=None,
    )
    divergence = _current_vs_ma20_divergence(technical_features)
    feature_fitness: dict[str, dict[str, Any]] = {}
    for feature in (
        basis.MA20, basis.MA50, basis.MA200, basis.RSI,
        basis.MOMENTUM_RETURN, basis.LOCAL_PRICE_ACTION,
    ):
        feature_fitness[feature] = {
            "basis_fitness": basis.evaluate_feature_fitness(
                feature=feature,
                current_context=context,
                history_context=context,
                observed_price_divergence_pct=divergence,
            ),
            "retained_feature_input_status": _feature_availability(feature, technical_features),
        }
    feature_fitness[basis.PIT_BACKTEST] = {
        "basis_fitness": basis.evaluate_feature_fitness(
            feature=basis.PIT_BACKTEST,
            current_context=context,
            history_context=context,
            decision_as_of=session,
        ),
        "retained_feature_input_status": "PIT_NOT_QUALIFIED_BY_CURRENT_RESEARCH_ARTIFACT",
    }
    feature_fitness[basis.EXECUTION_RAW_REPLAY] = {
        "basis_fitness": basis.evaluate_feature_fitness(
            feature=basis.EXECUTION_RAW_REPLAY,
            current_context=context,
            history_context=context,
        ),
        "retained_feature_input_status": "RAW_AS_TRADED_NOT_RETAINED_OR_PROMOTED",
    }
    corporate_events = (corporate_record or {}).get("corporate_action_context", {}).get("events") if isinstance(corporate_record, Mapping) else None
    no_retained_chain = not corporate_events
    corporate_chain = {
        "state": basis.BASIS_UNVERIFIED if no_retained_chain else "CORPORATE_ACTION_EVIDENCE_REQUIRES_SEPARATE_QUALIFICATION",
        "reason_codes": [basis.REASON_NO_QUALIFIED_FACTOR_CHAIN] if no_retained_chain else [basis.REASON_ADJUSTMENT_CHAIN_UNQUALIFIED],
        "event_count": len(corporate_events or []),
        "record_date_used_as_ex_date": False,
    }
    return {
        "ticker": ticker,
        "status": "RETAINED_CURRENT_RESEARCH_CONTEXT_OBSERVED",
        "observed_series": {
            "session": session,
            "technical_status": technical_features.get("status"),
            "technical_feature_as_of_session": technical_features.get("feature_as_of_session"),
            "technical_history_provenance": technical_features.get("technical_history_provenance"),
            "observed_basis_context": context,
            "current_to_ma20_divergence_pct": divergence,
            "numeric_divergence_authority_gate": False,
        },
        "current_vs_historical_basis": {
            # The same retained current-adjusted stream can support a local shadow comparison,
            # but it is not a verified reconstruction when there is no qualified event chain.
            # Keep that stricter question explicit so a plausible adjusted series never becomes
            # indistinguishable from an evidenced raw-to-adjusted reconciliation.
            "state": basis.BASIS_UNVERIFIED if no_retained_chain else feature_fitness[basis.MA20]["basis_fitness"]["state"],
            "reason_codes": [basis.REASON_NO_QUALIFIED_FACTOR_CHAIN] if no_retained_chain else feature_fitness[basis.MA20]["basis_fitness"]["reason_codes"],
            "note": "The current artifact declares a source-scoped retrospective-adjusted technical series. Local feature reads remain shadow/research-only; raw-to-adjusted reconstruction is unverified unless a qualified factor chain is retained.",
        },
        "corporate_action_factor_chain": corporate_chain,
        "feature_fitness": feature_fitness,
        "existing_signal_context": {
            "descriptive_trend_state": descriptive_record.get("trend_state"),
            "tactical_entry_state": tactical_record.get("entry_state") if isinstance(tactical_record, Mapping) else None,
            "tactical_entry_action": tactical_record.get("entry_action") if isinstance(tactical_record, Mapping) else None,
            "note": "Retained signal state is reported as context only; this diagnostic does not alter it or interpret it as an investment recommendation.",
        },
        "evidence_gaps": sorted(set(context.get("reason_codes") or []) | set(corporate_chain["reason_codes"])),
    }


def build_diagnostic(*, runtime_root: Path, session: str | None = None) -> dict[str, Any]:
    """Build a deterministic SSI/PNJ/PAN diagnostic from one governed retained session."""
    registry = _load_registry(runtime_root)
    selected_session = session or producer.resolve_latest_registered_completed_session(registry)
    inputs, metadata = session_operations.resolve_inputs(runtime_root, selected_session, registry)
    descriptive = inputs["descriptive"]
    corporate_intelligence = inputs["corporate_intelligence"]
    tactical = inputs["tactical"]
    descriptive_identity = (metadata.get("descriptive") or {}).get("artifact_identity")
    artifact = {
        "schema_version": "1.0.0",
        "contract_version": "price_basis_semantics_diagnostic/v1",
        "milestone": "PRICE_BASIS_SEMANTICS_AND_FEATURE_FITNESS_V1",
        "session": selected_session,
        "source_artifacts": {
            "descriptive": {
                "artifact_identity": descriptive_identity,
                "relative_path": (metadata.get("descriptive") or {}).get("path"),
            },
            "corporate_intelligence": {
                "artifact_identity": (metadata.get("corporate_intelligence") or {}).get("artifact_identity"),
                "relative_path": (metadata.get("corporate_intelligence") or {}).get("path"),
            },
            "tactical": {
                "artifact_identity": (metadata.get("tactical") or {}).get("artifact_identity"),
                "relative_path": (metadata.get("tactical") or {}).get("path"),
            },
        },
        "contract_summary": basis.contract_summary(),
        "cases": {
            ticker: _case(
                ticker=ticker,
                descriptive=descriptive,
                descriptive_identity=descriptive_identity,
                corporate_intelligence=corporate_intelligence,
                tactical=tactical,
                session=selected_session,
            )
            for ticker in REPRESENTATIVE_TICKERS
        },
        "authority_boundary": {
            "raw_as_traded": "NOT_PROMOTED",
            "historical_pit": "NOT_PROMOTED",
            "liquidity_execution_sizing": "UNCHANGED_AND_BLOCKED",
            "provider_authority": "UNCHANGED",
            "canonical_daily_classifications_modified": False,
            "record_date_inferred_as_ex_date": False,
            "provider_or_network_calls": False,
            "runtime_root_written": False,
        },
    }
    payload = json.loads(json.dumps(artifact, ensure_ascii=False, sort_keys=True))
    digest = basis._identity(payload)
    artifact["artifact_sha256"] = digest
    artifact["artifact_identity"] = f"price_basis_semantics_diagnostic:{digest}"
    return artifact


def write_diagnostic(path: Path, artifact: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, required=True, help="Read-only root holding the retained governed session artifacts.")
    parser.add_argument("--session", default=None, help="Explicit governed completed session (default: registry-selected latest).")
    parser.add_argument("--out", type=Path, default=None, help="Optional output artifact path in this checkout.")
    args = parser.parse_args(argv)
    artifact = build_diagnostic(runtime_root=args.runtime_root, session=args.session)
    if args.out:
        write_diagnostic(args.out, artifact)
    print(json.dumps({
        "session": artifact["session"],
        "artifact_identity": artifact["artifact_identity"],
        "case_states": {ticker: case.get("current_vs_historical_basis", {}).get("state") for ticker, case in artifact["cases"].items()},
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
