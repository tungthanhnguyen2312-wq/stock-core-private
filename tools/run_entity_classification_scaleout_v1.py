"""MARKET_WIDE_FINANCIAL_ENTITY_CLASSIFICATION_SCALEOUT_V1: scale-out promotion runner.

Reconciles the UNCLASSIFIED_GENERIC_FINANCIAL_ANALYSIS cohort of a retained Financial
Analysis V2 market-wide artifact against already-retained governed evidence (exchange
ICB industry sync, statement-template taxonomy, specialized legal-charter evidence -- see
entity_classification_scaleout.py for the reconciliation rules) and writes:

  1. config/promoted_entity_classifications_scaleout_v1.json -- the third Layered
     Authority Topology B tier (entity_classification_contract.py), strictly lower
     precedence than the seed CSV and the original P2E3 promoted manifest. Never
     overwrites either.
  2. operations-review/market-wide-financial-entity-classification-scaleout-v1-20260901/
     {exchange_industry_classification_snapshot.json, scaleout_classification_diagnostics.json,
     READINESS_REPORT.md} -- the generated evidence and per-ticker reconciliation trail.

Every input is read-only. No production/runtime write, no network.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import exchange_industry_classification as icb_mod  # noqa: E402
from entity_classification_contract import (  # noqa: E402
    DEFAULT_PROMOTED_CLASSIFICATIONS_PATH,
    DEFAULT_SCALEOUT_PROMOTED_CLASSIFICATIONS_PATH,
    DEFAULT_SEED_PROFILES_PATH,
    load_promoted_entity_classifications,
    load_seed_profiles,
)
from entity_classification_scaleout import ReconciliationInput, reconcile_ticker  # noqa: E402
from field_temporal_contract import stable_id  # noqa: E402
from statement_taxonomy_sidecar import load_sidecar, taxonomy_index  # noqa: E402

ARTIFACT_TYPE = "MARKET_WIDE_FINANCIAL_ENTITY_CLASSIFICATION_SCALEOUT_DIAGNOSTICS"
AUTHORITY_TYPE = "PROMOTED_ENTITY_CLASSIFICATION_REGISTRY"
# Defaults assume execution from a worktree two levels under the workspace root
# (StockLookup/worktrees/<name>/tools/this_file.py), matching how this milestone was
# implemented and how the shared evidence lake / runtime root are actually laid out on
# disk. Both are plain CLI overrides for any other checkout location (e.g. the primary
# stock-core-private checkout, one level shallower).
DEFAULT_CANONICAL_INSTRUMENT_ARTIFACT = (
    PROJECT_ROOT.parent.parent
    / "operations-review"
    / "p0-c1-canonical-instrument-reconciliation-20260816"
    / "data" / "canonical_instrument_reconciliation" / "artifacts"
    / "eb253a5a1a0601b90322265ee954bdb82f9751ab37994568c89d69a9ea16ba5d.json"
)
DEFAULT_RUNTIME_ROOT = PROJECT_ROOT.parent.parent / "dashboard-runtime"
DEFAULT_OUT_DIR = PROJECT_ROOT / "operations-review" / "market-wide-financial-entity-classification-scaleout-v1-20260901"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _candidate_universe(financial_analysis_context: Path) -> list[str]:
    engine = _load_json(financial_analysis_context)
    records = engine.get("records")
    if not isinstance(records, dict) or not records:
        raise SystemExit("FINANCIAL_ANALYSIS_CONTEXT_RECORDS_INVALID")
    return sorted(t for t, r in records.items() if r.get("analysis_family") == "UNCLASSIFIED_GENERIC_FINANCIAL_ANALYSIS")


def _canonical_index(path: Path) -> dict[str, dict]:
    data = _load_json(path)
    candidates = data.get("canonical_instrument_candidates")
    if not isinstance(candidates, list):
        raise SystemExit("CANONICAL_INSTRUMENT_ARTIFACT_INVALID")
    return {str(c.get("candidate_symbol", "")).upper().strip(): c for c in candidates}


def build_promotion(
    *,
    financial_analysis_context: Path,
    canonical_instrument_artifact: Path,
    runtime_root: Path,
    generated_at: str,
) -> tuple[dict, dict, dict]:
    """Return (promotion_payload, diagnostics_payload, industry_snapshot)."""
    candidates = _candidate_universe(financial_analysis_context)
    seed = load_seed_profiles(DEFAULT_SEED_PROFILES_PATH)
    original_promoted = load_promoted_entity_classifications(DEFAULT_PROMOTED_CLASSIFICATIONS_PATH)
    overlap = sorted((set(seed) | set(original_promoted)) & set(candidates))
    if overlap:
        # By construction UNCLASSIFIED_GENERIC_FINANCIAL_ANALYSIS excludes seed/promoted
        # tickers (see market_wide_financial_analysis_v2_scaleout.py); a non-empty overlap
        # means the supplied engine artifact is stale relative to current config. Fail
        # closed rather than silently re-deciding an already-governed ticker.
        raise SystemExit(f"CANDIDATE_OVERLAPS_EXISTING_AUTHORITY:{overlap[:10]}")

    c1_index = _canonical_index(canonical_instrument_artifact)
    industry_snapshot = icb_mod.build_industry_classification_snapshot(
        runtime_root, generated_at=generated_at,
        session_identity="market-wide-financial-entity-classification-scaleout-v1-20260901",
    )
    icb_index = icb_mod.industry_index(industry_snapshot)
    sidecar = load_sidecar(runtime_root)
    tax_index = taxonomy_index(sidecar)

    promoted_records: dict[str, dict] = {}
    diagnostics_rows: list[dict] = []
    outcome_counts: Counter = Counter()
    reason_counts: Counter = Counter()
    class_breakdown: Counter = Counter()
    source_resolved_by: Counter = Counter()
    conflicts: list[dict] = []
    not_applicable: list[dict] = []
    remaining_unknown: list[dict] = []

    for ticker in candidates:
        c1_rec = c1_index.get(ticker, {})
        selected = c1_rec.get("selected_fields", {}) if isinstance(c1_rec, dict) else {}
        legal_name = (selected.get("name") or {}).get("value")
        instrument_class = (selected.get("instrument_class") or {}).get("value")
        icb_rec = icb_index.get(ticker, {})
        inp = ReconciliationInput(
            ticker=ticker,
            issuer_identity=c1_rec.get("candidate_id") or f"issuer:{ticker}",
            legal_name=legal_name,
            instrument_class=instrument_class,
            icb_industry_hint=icb_rec.get("classification_hint"),
            icb_industry_label=icb_rec.get("icb_level_2_label"),
            icb_industry_reason=icb_rec.get("reason"),
            statement_taxonomy=tax_index.get(ticker),
        )
        result = reconcile_ticker(inp, verified_at=generated_at)
        outcome_counts[result.outcome] += 1
        reason_counts[result.reason_code.split(":")[0]] += 1
        row = {"ticker": ticker, "outcome": result.outcome, "reason_code": result.reason_code, "detail": result.detail}
        diagnostics_rows.append(row)

        if result.outcome == "CONFLICT":
            conflicts.append(row)
        elif result.outcome == "NOT_APPLICABLE":
            not_applicable.append(row)
        elif result.outcome == "UNKNOWN":
            remaining_unknown.append(row)
        else:
            assert result.record is not None
            class_breakdown[result.outcome] += 1
            source_resolved_by[result.record.evidence_tier.value] += 1
            promoted_records[ticker] = result.record.to_dict()

    promotion_payload = {
        "schema_version": "1.0.0",
        "contract_version": "entity_classification_contract/v1",
        "authority_type": AUTHORITY_TYPE,
        "authority_scope": "CURRENT_STATE_ONLY",
        "historical_pit_authority": "NOT_ESTABLISHED",
        "source_artifact_id": "market_wide_financial_entity_classification_scaleout/v1",
        "source_artifact_hash": industry_snapshot["records_fingerprint"],
        "source_seed_authority": "config/ticker_entity_profiles.csv",
        "source_original_promoted_authority": "config/promoted_entity_classifications.json",
        "promoted_at": generated_at,
        "promoted_record_count": len(promoted_records),
        "class_breakdown": {
            "corporate": class_breakdown.get("corporate", 0),
            "bank": class_breakdown.get("bank", 0),
            "securities": class_breakdown.get("securities", 0),
            "insurance": class_breakdown.get("insurance", 0),
            "finance_company": class_breakdown.get("finance_company", 0),
            "unknown": 0,
        },
        "promoted_records": promoted_records,
    }

    diagnostics_payload = {
        "schema_version": "1.0.0",
        "artifact_type": ARTIFACT_TYPE,
        "generated_at": generated_at,
        "candidate_denominator": len(candidates),
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "reason_code_counts": dict(sorted(reason_counts.items())),
        "classification_source_distribution": dict(sorted(source_resolved_by.items())),
        "conflicts": conflicts,
        "not_applicable": not_applicable,
        "remaining_unknown_count": len(remaining_unknown),
        "remaining_unknown_sample": remaining_unknown[:50],
        "rows": diagnostics_rows,
    }
    diagnostics_payload["diagnostics_identity"] = stable_id(
        {k: v for k, v in diagnostics_payload.items() if k != "diagnostics_identity"}
    )
    return promotion_payload, diagnostics_payload, industry_snapshot


def _readiness_report(promotion: dict, diagnostics: dict) -> str:
    oc = diagnostics["outcome_counts"]
    lines = [
        "# Market-Wide Financial Entity Classification Scale-Out V1",
        "",
        f"**Generated At**: `{diagnostics['generated_at']}`  ",
        f"**Candidate Denominator (UNCLASSIFIED_GENERIC_FINANCIAL_ANALYSIS)**: `{diagnostics['candidate_denominator']}`  ",
        f"**Newly Promoted**: `{promotion['promoted_record_count']}`  ",
        f"**Diagnostics Identity**: `{diagnostics['diagnostics_identity']}`  ",
        "",
        "## Outcome distribution",
        "",
        "| Outcome | Count |",
        "|---|---:|",
    ]
    for key in sorted(oc):
        lines.append(f"| `{key}` | {oc[key]} |")
    lines += ["", "## Classification source distribution", "", "| Evidence tier | Count |", "|---|---:|"]
    for key, val in sorted(diagnostics["classification_source_distribution"].items()):
        lines.append(f"| `{key}` | {val} |")
    lines += ["", "## Reason-code distribution", "", "| Reason code | Count |", "|---|---:|"]
    for key, val in sorted(diagnostics["reason_code_counts"].items()):
        lines.append(f"| `{key}` | {val} |")
    lines += [
        "",
        f"## Conflicts ({len(diagnostics['conflicts'])})",
        "",
    ]
    for row in diagnostics["conflicts"]:
        lines.append(f"- `{row['ticker']}`: {row['reason_code']}")
    lines += [
        "",
        f"## Not-applicable / unsupported security type ({len(diagnostics['not_applicable'])})",
        "",
    ]
    for row in diagnostics["not_applicable"]:
        lines.append(f"- `{row['ticker']}`: {row['reason_code']}")
    lines += [
        "",
        f"## Remaining unknown ({diagnostics['remaining_unknown_count']})",
        "",
        "Truthful residual: no positive, non-conflicting, non-heuristic evidence resolved these.",
        "",
    ]
    for row in diagnostics["remaining_unknown_sample"]:
        lines.append(f"- `{row['ticker']}`: {row['reason_code']}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--financial-analysis-context", type=Path, required=True,
                        help="Retained financial_analysis_context/v2 market-wide artifact "
                             "(the current, pre-scaleout run) supplying the candidate universe.")
    parser.add_argument("--canonical-instrument-artifact", type=Path, default=DEFAULT_CANONICAL_INSTRUMENT_ARTIFACT)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--promoted-output", type=Path, default=DEFAULT_SCALEOUT_PROMOTED_CLASSIFICATIONS_PATH)
    parser.add_argument("--generated-at", default=None)
    args = parser.parse_args()

    generated_at = args.generated_at or datetime.now(timezone.utc).isoformat()
    promotion, diagnostics, industry_snapshot = build_promotion(
        financial_analysis_context=args.financial_analysis_context,
        canonical_instrument_artifact=args.canonical_instrument_artifact,
        runtime_root=args.runtime_root,
        generated_at=generated_at,
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "exchange_industry_classification_snapshot.json").write_text(
        json.dumps(industry_snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.out_dir / "scaleout_classification_diagnostics.json").write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (args.out_dir / "READINESS_REPORT.md").write_text(_readiness_report(promotion, diagnostics), encoding="utf-8")

    args.promoted_output.parent.mkdir(parents=True, exist_ok=True)
    args.promoted_output.write_text(
        json.dumps(promotion, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps({
        "candidate_denominator": diagnostics["candidate_denominator"],
        "promoted_record_count": promotion["promoted_record_count"],
        "class_breakdown": promotion["class_breakdown"],
        "outcome_counts": diagnostics["outcome_counts"],
        "conflicts": len(diagnostics["conflicts"]),
        "not_applicable": len(diagnostics["not_applicable"]),
        "remaining_unknown": diagnostics["remaining_unknown_count"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
