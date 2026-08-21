"""Operational runner for Wave 2 official financial evidence scale-out.

Produces:
1. operations-review/official-financial-evidence-scaleout-wave2-20260821/wave2_official_financial_evidence_scaleout_artifact.json
2. operations-review/official-financial-evidence-scaleout-wave2-20260821/wave2_official_financial_evidence_scaleout_summary.md
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wave2_official_financial_evidence_scaleout import execute
OUTPUT_DIR = ROOT / "operations-review" / "official-financial-evidence-scaleout-wave2-20260821"
ARTIFACT_PATH = OUTPUT_DIR / "wave2_official_financial_evidence_scaleout_artifact.json"
SUMMARY_PATH = OUTPUT_DIR / "wave2_official_financial_evidence_scaleout_summary.md"


def render_summary(artifact: dict[str, Any]) -> str:
    cohort = artifact["cohort_identity"]
    cmp = artifact["before_after_comparison"]
    candidates = artifact["wave2_candidate_cohort"]
    evals = artifact["wave2_candidate_evaluations"]
    disc_summary = artifact["source_discovery_summary"]
    blockers = artifact["root_blocker_distribution"]
    boundaries = artifact["authority_boundaries"]

    lines = [
        "# Wave 2 Official Financial Evidence Scale-Out Summary",
        "",
        f"- **Artifact Identity**: `{artifact['artifact_identity']}`",
        f"- **Contract Version**: `{artifact['contract_version']}`",
        f"- **Scaleout Gate**: `{artifact['scaleout_gate']}`",
        f"- **Verdict**: `{artifact['verdict']}`",
        "",
        "## 1. Candidate Cohort Selection & Rationale",
        "",
        f"- **Total Empirical Cohort**: {cohort['total_cohort_count']} members",
        f"- **Target Blocked Universe**: {cohort['target_blocked_cohort_count']} members",
        f"- **Wave 2 Candidate Count**: {cohort['wave2_candidate_cohort_count']} bounded candidates",
        "",
        "| Ticker | Sector | Selection Reasons |",
        "|---|---|---|",
    ]

    for c in candidates:
        reasons = ", ".join(c["selection_reasons"])
        lines.append(f"| `{c['ticker']}` | {c['entity_type']} | {reasons} |")

    lines.extend([
        "",
        "## 2. Official Source Discovery & Route Ownership Evaluation",
        "",
        f"- **Total Candidates Attempted**: {disc_summary['total_candidates_attempted']}",
        "- **Discovery Dispositions**:",
    ])
    for disp, cnt in disc_summary["disposition_counts"].items():
        lines.append(f"  - `{disp}`: {cnt}")
    lines.append("- **Route Ownership Status**:")
    for status, cnt in disc_summary["route_ownership_status_counts"].items():
        lines.append(f"  - `{status}`: {cnt}")

    lines.extend([
        "",
        "| Ticker | Sector | Candidate Disposition | Discovery Status | Route Ownership Status | Retained Filings |",
        "|---|---|---|---|---|---|",
    ])
    for e in evals:
        lines.append(
            f"| `{e['ticker']}` | {e['entity_type']} | `{e['disposition']}` | `{e['discovery_disposition']}` | `{e['route_ownership_status']}` | {e['retained_documents_count']} |"
        )

    lines.extend([
        "",
        "## 3. Before vs. After Research Readiness & Coverage",
        "",
        "| Metric / Dimension | Baseline (P3-F13) | Wave 2 Scaleout | Delta |",
        "|---|---|---|---|",
        f"| **Official Filings Retained / Acquired** | {cmp['official_filings_acquired_or_retained']['before']} | {cmp['official_filings_acquired_or_retained']['after']} | {cmp['official_filings_acquired_or_retained']['delta']} |",
        f"| **Metadata Qualified Issuers** | {cmp['metadata_qualified_issuers']['before']} | {cmp['metadata_qualified_issuers']['after']} | {cmp['metadata_qualified_issuers']['delta']} |",
        f"| **Value Qualified Issuers** | {cmp['value_qualified_issuers']['before']} | {cmp['value_qualified_issuers']['after']} | {cmp['value_qualified_issuers']['delta']} |",
        f"| **Canonical Exact Qualified Facts** | {cmp['canonical_exact_qualified_facts']['before']} | {cmp['canonical_exact_qualified_facts']['after']} | {cmp['canonical_exact_qualified_facts']['delta']} |",
        f"| **P3-B Exact Qualified Metrics** | {cmp['exact_qualified_metrics']['before']} | {cmp['exact_qualified_metrics']['after']} | {cmp['exact_qualified_metrics']['delta']} |",
        f"| **P3-B Derived Proxies** | {cmp['derived_proxies']['before']} | {cmp['derived_proxies']['after']} | {cmp['derived_proxies']['delta']} |",
        f"| **P3-B Missing Metrics** | {cmp['missing_metrics']['before']} | {cmp['missing_metrics']['after']} | {cmp['missing_metrics']['delta']} |",
        f"| **Fundamental Readiness: Complete** | {cmp['fundamental_readiness_status']['before']['COMPLETE']} | {cmp['fundamental_readiness_status']['after']['COMPLETE']} | {cmp['fundamental_readiness_status']['after']['COMPLETE'] - cmp['fundamental_readiness_status']['before']['COMPLETE']} |",
        f"| **Fundamental Readiness: Partial** | {cmp['fundamental_readiness_status']['before']['PARTIAL']} | {cmp['fundamental_readiness_status']['after']['PARTIAL']} | {cmp['fundamental_readiness_status']['after']['PARTIAL'] - cmp['fundamental_readiness_status']['before']['PARTIAL']} |",
        f"| **Fundamental Readiness: Blocked** | {cmp['fundamental_readiness_status']['before']['BLOCKED']} | {cmp['fundamental_readiness_status']['after']['BLOCKED']} | {cmp['fundamental_readiness_status']['after']['BLOCKED'] - cmp['fundamental_readiness_status']['before']['BLOCKED']} |",
        "",
        "## 4. Root Blocker Distribution",
        "",
        "| Root Cause | Affected Instruments | Description |",
        "|---|---|---|",
    ])
    for b in blockers:
        lines.append(f"| `{b['root_cause']}` | {b['affected_instruments']} | {b['description']} |")

    lines.extend([
        "",
        "## 5. Authority Boundaries & Invariants",
        "",
        f"- **New Provider Added**: `{boundaries['new_provider_added']}`",
        f"- **Source Authority Promoted**: `{boundaries['source_authority_promoted']}`",
        f"- **Canonical Store Mutated**: `{boundaries['canonical_store_mutated']}`",
        f"- **Runtime DB Mutated**: `{boundaries['runtime_database_mutated']}`",
        f"- **Historical PIT Promoted**: `{boundaries['historical_pit_promoted']}`",
        f"- **Raw as Traded Promoted**: `{boundaries['raw_as_traded_promoted']}`",
        f"- **Liquidity Sizing Promoted**: `{boundaries['liquidity_sizing_promoted']}`",
        f"- **Valuation / Recommendation Produced**: `{boundaries['valuation_or_recommendation_produced']}`",
        f"- **P3-G Started**: `{boundaries['p3g_started']}`",
        f"- **Ticker-Specific Branch Audit**: `{artifact['ticker_specific_branch_audit']['status']}`",
        "",
        "## 6. Next Operational Gate",
        "",
        f"`{artifact['next_gate']}`",
    ])

    return "\n".join(lines) + "\n"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    artifact = execute()

    ARTIFACT_PATH.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"Wrote artifact to {ARTIFACT_PATH}")

    summary = render_summary(artifact)
    SUMMARY_PATH.write_text(summary, encoding="utf-8")
    print(f"Wrote summary to {SUMMARY_PATH}")
    print(f"Identity: {artifact['artifact_identity']}")
    print(f"Verdict: {artifact['verdict']}")


if __name__ == "__main__":
    main()
