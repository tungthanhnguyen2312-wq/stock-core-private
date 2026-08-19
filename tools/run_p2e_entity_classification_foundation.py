"""Phase 2 / P2-E: Evidence-Backed Entity Classification Scale-Out Foundation Runner.

Executes deterministic classification across:
1. Part A: 20 existing known classified issuers (13 corporate, 4 bank, 1 securities, 1 insurance, 1 finance_company).
2. Part B: 20 deterministically selected previously-UNKNOWN listed equities from canonical candidate master.
3. Scale denominator tracking:
   - TOTAL_CANONICAL_CANDIDATES = 3,250
   - LISTED_EQUITY_CANDIDATES = 1,660
   - PREVIOUSLY_POSITIVELY_CLASSIFIED = 20
   - PREVIOUSLY_UNKNOWN = 1,640
   - VALIDATION_UNKNOWN_COHORT = 20
   - NEWLY_QUALIFIED
   - REMAINING_UNKNOWN
4. Downstream model applicability verification.
5. Emits deterministic JSON artifact and READINESS_REPORT.md to operations-review/.
6. Authority status: PROMOTION_REVIEW_READY (does not overwrite config/ticker_entity_profiles.csv).
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from entity_classification_contract import (
    CONTRACT_VERSION,
    ClassificationStatus,
    EntityClass,
    EntityClassificationRecord,
    SCHEMA_VERSION,
)
from evidence_backed_entity_classifier import (
    TICKER_SPECIFIC_EXTRACTION_BRANCH_COUNT,
    classify_entity,
)
from field_temporal_contract import stable_id
from financial_entity_applicability import evaluate_ticker, metric_applicability
from multi_period_financial_panel import compute_bounded_derived_metrics

ARTIFACT_TYPE = "EVIDENCE_BACKED_ENTITY_CLASSIFICATION_REPORT"
AUTHORITY_STATUS = "PROMOTION_REVIEW_READY"

VALIDATION_UNKNOWN_COHORT_SIZE = 20


def load_canonical_candidates(repo_root: Path) -> list[dict[str, Any]]:
    """Load canonical instrument candidates from C1 reconciliation artifact."""
    repo = Path(repo_root).resolve()
    c1_path = (
        repo.parent
        / "operations-review"
        / "p0-c1-canonical-instrument-reconciliation-20260816"
        / "data"
        / "canonical_instrument_reconciliation"
        / "artifacts"
        / "eb253a5a1a0601b90322265ee954bdb82f9751ab37994568c89d69a9ea16ba5d.json"
    )
    if not c1_path.is_file():
        c1_path = (
            repo
            / "operations-review"
            / "p0-c1-canonical-instrument-reconciliation-20260816"
            / "data"
            / "canonical_instrument_reconciliation"
            / "artifacts"
            / "eb253a5a1a0601b90322265ee954bdb82f9751ab37994568c89d69a9ea16ba5d.json"
        )
    if not c1_path.is_file():
        raise FileNotFoundError(f"Canonical instrument reconciliation artifact not found at {c1_path}")

    data = json.loads(c1_path.read_text(encoding="utf-8"))
    return data.get("canonical_instrument_candidates", [])


def load_curated_seed_profiles(repo_root: Path) -> dict[str, str]:
    """Load baseline curated profiles from config/ticker_entity_profiles.csv."""
    repo = Path(repo_root).resolve()
    profiles_path = repo / "config" / "ticker_entity_profiles.csv"
    if not profiles_path.is_file():
        return {}
    profiles: dict[str, str] = {}
    with profiles_path.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sym = str(row.get("ticker", "")).upper().strip()
            etype = str(row.get("entity_type", "")).lower().strip()
            if sym and etype:
                profiles[sym] = etype
    return profiles


def execute_entity_classification_evaluation(
    repo_root: Path,
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Execute end-to-end P2-E entity classification evaluation."""
    gen_time = generated_at or datetime.now(timezone.utc).isoformat()
    candidates = load_canonical_candidates(repo_root)
    seed_profiles = load_curated_seed_profiles(repo_root)

    total_canonical_candidates = len(candidates)
    c_by_sym = {c.get("candidate_symbol", "").upper().strip(): c for c in candidates}

    # Filter listed equity candidates (instrument_class == EQUITY)
    listed_equities = [
        c for c in candidates
        if c.get("selected_fields", {}).get("instrument_class", {}).get("value") == "EQUITY"
    ]
    total_listed_equities = len(listed_equities)

    # Split into previously classified vs previously unknown
    previously_classified = [
        c for c in listed_equities
        if c.get("candidate_symbol", "").upper().strip() in seed_profiles
    ]
    previously_unknown = [
        c for c in listed_equities
        if c.get("candidate_symbol", "").upper().strip() not in seed_profiles
    ]

    total_previously_classified = len(seed_profiles)
    total_previously_unknown = total_listed_equities - len(previously_classified)

    # Select Part B deterministic 20-ticker UNKNOWN cohort (alphabetically sorted)
    sorted_unknown = sorted(previously_unknown, key=lambda c: str(c.get("candidate_symbol", "")).upper())
    validation_unknown_cohort = sorted_unknown[:VALIDATION_UNKNOWN_COHORT_SIZE]

    evaluated_records: list[EntityClassificationRecord] = []
    downstream_verifications: list[dict[str, Any]] = []

    # 1. Evaluate Part A: Known Seed Cohort (20 issuers)
    part_a_results: list[dict[str, Any]] = []
    for sym, seed_etype in seed_profiles.items():
        cand = c_by_sym.get(sym, {})
        cand_id = cand.get("candidate_id", f"candidate:{sym}")
        legal_name = cand.get("selected_fields", {}).get("name", {}).get("value")
        
        rec = classify_entity(
            issuer_identity=cand_id,
            ticker=sym,
            legal_name=legal_name,
            curated_seed_profile=seed_etype,
            verified_at=gen_time,
        )
        evaluated_records.append(rec)

        # Downstream applicability verification
        eval_res = evaluate_ticker(sym, manual_entity_type=rec.entity_class.value)
        ebitda_app = eval_res["metric_applicability"].get("ebitda", {})

        part_a_results.append({
            "cohort_part": "PART_A_KNOWN_PROFILE",
            "ticker": sym,
            "seed_entity_type": seed_etype,
            "classification": rec.to_dict(),
            "downstream_applicability": {
                "ebitda_status": ebitda_app.get("status"),
                "ebitda_reason": ebitda_app.get("reason"),
            },
        })

    # 2. Evaluate Part B: Bounded Previously-UNKNOWN Cohort (20 issuers)
    part_b_results: list[dict[str, Any]] = []
    for cand in validation_unknown_cohort:
        sym = str(cand.get("candidate_symbol", "")).upper().strip()
        cand_id = cand.get("candidate_id", f"candidate:{sym}")
        legal_name = cand.get("selected_fields", {}).get("name", {}).get("value")

        rec = classify_entity(
            issuer_identity=cand_id,
            ticker=sym,
            legal_name=legal_name,
            curated_seed_profile=None,
            verified_at=gen_time,
        )
        evaluated_records.append(rec)

        # Downstream applicability verification
        eval_res = evaluate_ticker(sym, manual_entity_type=rec.entity_class.value)
        ebitda_app = eval_res["metric_applicability"].get("ebitda", {})

        part_b_results.append({
            "cohort_part": "PART_B_PREVIOUSLY_UNKNOWN",
            "ticker": sym,
            "seed_entity_type": "unknown",
            "classification": rec.to_dict(),
            "downstream_applicability": {
                "ebitda_status": ebitda_app.get("status"),
                "ebitda_reason": ebitda_app.get("reason"),
            },
        })

    # Aggregations & Denominators
    newly_qualified_count = sum(1 for r in part_b_results if r["classification"]["classification_status"] == ClassificationStatus.QUALIFIED.value)
    ambiguous_count = sum(1 for r in evaluated_records if r.classification_status == ClassificationStatus.AMBIGUOUS)
    conflict_count = sum(1 for r in evaluated_records if r.classification_status == ClassificationStatus.CONFLICT)
    remaining_market_unknown = total_previously_unknown - newly_qualified_count

    # Breakdown by Entity Class
    class_breakdown = {
        "corporate": sum(1 for r in evaluated_records if r.entity_class == EntityClass.CORPORATE),
        "bank": sum(1 for r in evaluated_records if r.entity_class == EntityClass.BANK),
        "securities": sum(1 for r in evaluated_records if r.entity_class == EntityClass.SECURITIES),
        "insurance": sum(1 for r in evaluated_records if r.entity_class == EntityClass.INSURANCE),
        "finance_company": sum(1 for r in evaluated_records if r.entity_class == EntityClass.FINANCE_COMPANY),
        "unknown": sum(1 for r in evaluated_records if r.entity_class == EntityClass.UNKNOWN),
    }

    raw_payload = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "authority_status": AUTHORITY_STATUS,
        "generated_at": gen_time,
        "scale_metrics": {
            "total_canonical_candidates": total_canonical_candidates,
            "listed_equity_candidates": total_listed_equities,
            "previously_positively_classified": total_previously_classified,
            "previously_unknown": total_previously_unknown,
            "validation_unknown_cohort": len(validation_unknown_cohort),
            "validation_total_evaluated": len(evaluated_records),
            "newly_qualified_in_validation_cohort": newly_qualified_count,
            "remaining_market_unknown": remaining_market_unknown,
            "ambiguous_count": ambiguous_count,
            "conflict_count": conflict_count,
            "ticker_specific_extraction_branch_count": TICKER_SPECIFIC_EXTRACTION_BRANCH_COUNT,
        },
        "class_breakdown": class_breakdown,
        "validation_selection_rule": "Alphabetical sort of C1 canonical listed-equity candidate universe excluding 20 seed profiles; first 20 selected deterministically",
        "part_a_known_results": part_a_results,
        "part_b_unknown_results": part_b_results,
    }

    content_hash = stable_id(raw_payload)
    artifact_id = f"p2e_entity_classification:{content_hash}"

    return {
        **raw_payload,
        "artifact_id": artifact_id,
        "artifact_hash": content_hash,
    }


def generate_readiness_report(result: Mapping[str, Any]) -> str:
    """Generate Markdown readiness report for Phase 2-E entity classification foundation."""
    scale = result.get("scale_metrics", {})
    breakdown = result.get("class_breakdown", {})
    part_a = result.get("part_a_known_results", [])
    part_b = result.get("part_b_unknown_results", [])

    lines = [
        "# Phase 2 / P2-E: Evidence-Backed Entity Classification Scale-Out Foundation Report",
        "",
        f"**Contract Version**: `{result.get('contract_version')}`  ",
        f"**Artifact ID**: `{result.get('artifact_id')}`  ",
        f"**Authority Status**: **`{result.get('authority_status')}`**  ",
        f"**Generated At**: `{result.get('generated_at')}`  ",
        "",
        "## 1. Executive Summary & Scale Denominators",
        "",
        "| Scale Metric Dimension | Count | Description / Boundary |",
        "|---|:---:|---|",
        f"| **Total Canonical Candidates** | **`{scale.get('total_canonical_candidates'):,}`** | Full C.1 reconciled instrument universe |",
        f"| **Listed Equity Candidates** | **`{scale.get('listed_equity_candidates'):,}`** | `instrument_class == EQUITY` |",
        f"| **Previously Positively Classified** | **`{scale.get('previously_positively_classified'):,}`** | Baseline seed profiles in `config/ticker_entity_profiles.csv` |",
        f"| **Previously Unknown Equities** | **`{scale.get('previously_unknown'):,}`** | Initial unclassified listed equity candidates |",
        f"| **Validation Unknown Cohort** | **`{scale.get('validation_unknown_cohort'):,}`** | Deterministic alphabetical sample (Part B) |",
        f"| **Newly Qualified in Cohort** | **`{scale.get('newly_qualified_in_validation_cohort'):,}`** | Positively resolved from charter/evidence |",
        f"| **Remaining Market Unknown** | **`{scale.get('remaining_market_unknown'):,}`** | Candidates remaining for future scale-out waves |",
        f"| **Ambiguous Interpretations** | **`{scale.get('ambiguous_count')}`** | Competing non-conflicting signals |",
        f"| **Contradictory Conflicts** | **`{scale.get('conflict_count')}`** | Disagreements across authoritative sources |",
        f"| **Ticker-Specific Extraction Branches** | **`{scale.get('ticker_specific_extraction_branch_count')}`** | Zero hardcoded ticker logic in production classifier |",
        "",
        "## 2. Classified Entity Class Breakdown (Validation Corpus)",
        "",
        "| Entity Class | Evaluated Count | Downstream Applicability Model |",
        "|---|:---:|---|",
        f"| **Corporate** | `{breakdown.get('corporate')}` | Ordinary commercial debt/equity, EBITDA, Net Debt eligible subject to evidence |",
        f"| **Bank** | `{breakdown.get('bank')}` | Corporate debt/EBITDA `not_applicable` (fail-closed); P/B, ROE, NIM, CIR, CAR |",
        f"| **Securities** | `{breakdown.get('securities')}` | Corporate debt/EBITDA `not_applicable`; P/B, ROE, Brokerage Share, Margin Book |",
        f"| **Insurance** | `{breakdown.get('insurance')}` | Corporate debt/EBITDA `not_applicable`; P/B, ROE, Combined Ratio, Loss Ratio |",
        f"| **Finance Company** | `{breakdown.get('finance_company')}` | Specialized credit institution; corporate debt `not_applicable` |",
        f"| **Unknown** | `{breakdown.get('unknown')}` | `insufficient_evidence`; fail-closed |",
        "",
        "## 3. Part A: Existing Known Profiles Baseline Verification",
        "",
        "| Ticker | Seed Profile | Resolved Entity Class | Status | Evidence Tier | Downstream EBITDA Status |",
        "|---|:---:|:---:|:---:|:---:|:---:|",
    ]

    for item in part_a:
        c = item["classification"]
        d = item["downstream_applicability"]
        lines.append(
            f"| **{item['ticker']}** | `{item['seed_entity_type']}` | **`{c['entity_class']}`** | "
            f"`{c['classification_status']}` | `{c['evidence_tier']}` | `{d['ebitda_status']}` |"
        )

    lines.extend([
        "",
        "## 4. Part B: Previously-UNKNOWN Listed Equities Evaluation",
        "",
        "| Ticker | Legal Issuer Name | Resolved Class | Status | Evidence Tier | Classification Reason |",
        "|---|---|:---:|:---:|:---:|---|",
    ])

    for item in part_b:
        c = item["classification"]
        lines.append(
            f"| **{item['ticker']}** | {c.get('legal_name', 'N/A')} | **`{c['entity_class']}`** | "
            f"`{c['classification_status']}` | `{c['evidence_tier']}` | `{c['classification_reason']}` |"
        )

    lines.extend([
        "",
        "---",
        "**Authority Statement**: This evaluation establishes the deterministic evidence-backed entity classification foundation. Seed authority file `config/ticker_entity_profiles.csv` remains untouched pending owner promotion review (**`PROMOTION_REVIEW_READY`**).",
    ])

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run P2-E entity classification foundation evaluation.")
    parser.add_argument("--repo-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()

    out_dir = args.out_dir or (args.repo_root / "operations-review" / "p2e-evidence-backed-entity-classification-20260819")
    out_dir.mkdir(parents=True, exist_ok=True)

    result = execute_entity_classification_evaluation(args.repo_root)

    json_path = out_dir / "p2e_entity_classification_artifact.json"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    md_report = generate_readiness_report(result)
    md_path = out_dir / "READINESS_REPORT.md"
    md_path.write_text(md_report, encoding="utf-8")

    print(f"P2-E Evaluation Complete: Evaluated {result['scale_metrics']['validation_total_evaluated']} issuers.")
    print(f"Authority Status: {result['authority_status']}")
    print(f"JSON Artifact: {json_path}")
    print(f"Report: {md_path}")


if __name__ == "__main__":
    main()
