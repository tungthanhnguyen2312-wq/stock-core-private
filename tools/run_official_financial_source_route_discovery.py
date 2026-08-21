"""Operational runner for Official Financial Source Route Discovery V1.

Produces:
1. operations-review/official-financial-source-route-discovery-v1-20260821/official_financial_source_route_discovery_artifact.json
2. operations-review/official-financial-source-route-discovery-v1-20260821/official_financial_source_route_discovery_summary.md
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from official_financial_source_route_discovery import execute


OUTPUT_DIR = ROOT / "operations-review" / "official-financial-source-route-discovery-v1-20260821"
ARTIFACT_PATH = OUTPUT_DIR / "official_financial_source_route_discovery_artifact.json"
SUMMARY_PATH = OUTPUT_DIR / "official_financial_source_route_discovery_summary.md"


def render_summary(artifact: dict[str, Any]) -> str:
    cohort = artifact["validation_cohort_identity"]
    counts = artifact["summary_counts"]
    evals = artifact["route_evaluations"]
    candidates = artifact["governed_registry_candidates"]
    boundaries = artifact["authority_boundaries"]
    gov = artifact["governance_separation"]

    lines = [
        "# Official Financial Source Route Discovery V1 Summary",
        "",
        f"- **Artifact Identity**: `{artifact['artifact_identity']}`",
        f"- **Contract Version**: `{artifact['contract_version']}`",
        f"- **Verdict**: `{artifact['verdict']}`",
        f"- **Next Operational Gate**: `{artifact['next_gate']}`",
        "",
        "## 1. Executive Summary & Counts",
        "",
        f"- **Validation Cohort Size**: {cohort['candidate_count']} issuers",
        f"- **Total Route Evaluations**: {counts['total_route_evaluations']} routes",
        f"- **Ownership Qualified Routes**: {counts['ownership_qualified_routes']}",
        f"- **Rejected Routes**: {counts['rejected_routes']}",
        f"- **Discovered Unqualified Routes**: {counts['discovered_unqualified_routes']}",
        f"- **Not Found Routes**: {counts['not_found_routes']}",
        f"- **Governed Registry Candidates Proposed**: {counts['new_governed_registry_candidates_proposed']}",
        "",
        "## 2. Route Evaluations by Ticker",
        "",
        "| Ticker | Legal Identity | Route Class | Candidate URL | Probe Status | Route Status | Ownership Evidence / Reason |",
        "|---|---|---|---|---|---|---|",
    ]

    for r in evals:
        evidence_text = r.get("ownership_evidence_span") or r.get("rejection_reason") or "None"
        # Truncate long evidence text for clean table rendering
        if len(evidence_text) > 80:
            evidence_text = evidence_text[:77] + "..."
        lines.append(
            f"| `{r['ticker']}` | {r['legal_issuer_identity']} | `{r['route_class']}` | `{r['candidate_url']}` | `{r['probe_status']}` | `{r['route_status']}` | {evidence_text} |"
        )

    lines.extend([
        "",
        "## 3. Governed Registry Candidates (Pending Owner Promotion)",
        "",
        "| Ticker | Legal Issuer Identity | Candidate Host | Candidate URL | Ownership Evidence Type | Recommendation |",
        "|---|---|---|---|---|---|",
    ])

    for gc in candidates:
        lines.append(
            f"| `{gc['ticker']}` | {gc['legal_issuer_identity']} | `{gc['candidate_host']}` | `{gc['candidate_url']}` | `{gc['ownership_evidence_type']}` | `{gc['activation_recommendation']}` |"
        )

    lines.extend([
        "",
        "## 4. Governance & Authority Separation",
        "",
        f"- **Discovery Performed**: `{gov['discovery_performed']}`",
        f"- **Registry Mutated**: `{gov['registry_mutated']}`",
        f"- **Activation Promoted**: `{gov['activation_promoted']}`",
        f"- **Financial Documents Acquired**: `{gov['financial_documents_acquired']}`",
        f"- **Financial Facts Created**: `{gov['financial_facts_created']}`",
        f"- **Fundamental Readiness Mutated**: `{gov['fundamental_readiness_mutated']}`",
        "",
        "## 5. Authority Boundaries & Invariants",
        "",
        f"- **New Provider Added**: `{boundaries['new_provider_added']}`",
        f"- **Source Authority Promoted**: `{boundaries['source_authority_promoted']}`",
        f"- **Canonical Store Mutated**: `{boundaries['canonical_store_mutated']}`",
        f"- **Runtime DB Mutated**: `{boundaries['runtime_database_mutated']}`",
        f"- **Raw as Traded Promoted**: `{boundaries['raw_as_traded_promoted']}`",
        f"- **Liquidity Sizing Promoted**: `{boundaries['liquidity_sizing_promoted']}`",
        f"- **Valuation / Recommendation Produced**: `{boundaries['valuation_or_recommendation_produced']}`",
        f"- **P3-G Started**: `{boundaries['p3g_started']}`",
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
