"""Operational runner for Retained Official Route Ownership Evidence Acquisition V1.

Produces:
1. operations-review/retained-official-route-ownership-evidence-20260821/retained_official_route_ownership_evidence_artifact.json
2. operations-review/retained-official-route-ownership-evidence-20260821/retained_official_route_ownership_evidence_summary.md
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from retained_official_route_ownership_evidence import execute


OUTPUT_DIR = ROOT / "operations-review" / "retained-official-route-ownership-evidence-20260821"
ARTIFACT_PATH = OUTPUT_DIR / "retained_official_route_ownership_evidence_artifact.json"
SUMMARY_PATH = OUTPUT_DIR / "retained_official_route_ownership_evidence_summary.md"


def render_summary(artifact: dict[str, Any]) -> str:
    cohort = artifact["validation_cohort_identity"]
    ev_summary = artifact["retained_evidence_summary"]
    candidates = artifact["governed_registry_candidates_proposed"]
    gov = artifact["governance_separation"]
    boundaries = artifact["authority_boundaries"]

    lines = [
        "# Retained Official Route Ownership Evidence Acquisition V1 Summary",
        "",
        f"- **Artifact Identity**: `{artifact['artifact_identity']}`",
        f"- **Contract Version**: `{artifact['contract_version']}`",
        f"- **Verdict**: `{artifact['verdict']}`",
        f"- **Next Operational Gate**: `{artifact['next_gate']}`",
        "",
        "## 1. Acquisition & Retention Metrics",
        "",
        f"- **Validation Cohort Size**: {cohort['candidate_count']} issuers",
        f"- **Network Probes Attempted**: {ev_summary['network_probes_attempted']}",
        f"- **Retained Evidence Objects Acquired & Hashed**: {ev_summary['retained_evidence_objects_count']}",
        f"- **Technical Failures / Unreachable Routes**: {ev_summary['technical_acquisition_failures_count']}",
        f"- **Governed Registry Candidates Proposed**: {len(candidates)}",
        "",
        "## 2. Retained First-Party Ownership Evidence Objects",
        "",
        "| Ticker | Legal Issuer Identity | Candidate URL | Retained Bytes | SHA-256 (Content Identity) | Evidence Span / Statutory Text |",
        "|---|---|---|---|---|---|",
    ]

    for rec in ev_summary["retained_evidence_objects"]:
        span = rec["extracted_identity_fields"]["statutory_registration_span"]
        if len(span) > 70:
            span = span[:67] + "..."
        lines.append(
            f"| `{rec['canonical_instrument']}` | {rec['issuer_legal_identity']} | `{rec['candidate_locator']}` | {rec['content_bytes_length']:,} B | `{rec['raw_document_sha256'][:16]}...` | {span} |"
        )

    lines.extend([
        "",
        "## 3. Technical Acquisition Failures & Fail-Closed Dispositions",
        "",
        "| Ticker | Candidate URL | Technical Disposition | Error / Reason |",
        "|---|---|---|---|",
    ])

    for ticker, tf in sorted(ev_summary["technical_failures"].items()):
        lines.append(
            f"| `{ticker}` | `{tf['candidate_url']}` | `{tf['failure_disposition']}` | {tf['error']} |"
        )

    lines.extend([
        "",
        "## 4. Governed Registry Candidates (Pending Owner Promotion)",
        "",
        "| Ticker | Legal Issuer Identity | Candidate Host | Candidate URL | Retained File Path | Recommendation |",
        "|---|---|---|---|---|---|",
    ])

    for gc in candidates:
        lines.append(
            f"| `{gc['ticker']}` | {gc['legal_issuer_identity']} | `{gc['candidate_host']}` | `{gc['candidate_url']}` | `{gc['retained_evidence_path']}` | `{gc['activation_recommendation']}` |"
        )

    lines.extend([
        "",
        "## 5. Governance & Authority Separation",
        "",
        f"- **Evidence Retained on Disk**: `{gov['evidence_retained']}`",
        f"- **Registry Mutated**: `{gov['registry_mutated']}`",
        f"- **Activation Promoted**: `{gov['activation_promoted']}`",
        f"- **Financial Documents Acquired**: `{gov['financial_documents_acquired']}`",
        f"- **Financial Facts Created**: `{gov['financial_facts_created']}`",
        f"- **Fundamental Readiness Mutated**: `{gov['fundamental_readiness_mutated']}`",
        "",
        "## 6. Authority Boundaries & Invariants",
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
