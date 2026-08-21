"""Run the bounded official route evidence enrichment execution V1."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from bounded_official_route_evidence_enrichment import (
    execute_bounded_enrichment,
    OPERATIONS_REVIEW_DIR,
    ENRICHMENT_EVIDENCE_DIR,
)

OUTPUT_ARTIFACT = OPERATIONS_REVIEW_DIR / "bounded_official_route_evidence_enrichment_artifact.json"
OUTPUT_SUMMARY = OPERATIONS_REVIEW_DIR / "bounded_official_route_evidence_enrichment_summary.md"


def _generate_summary_markdown(artifact: dict) -> str:
    lines = [
        "# Bounded Official Route Evidence Enrichment V1 — Summary",
        "",
        f"- **Verdict**: `{artifact['verdict']}`",
        f"- **Contract Version**: `{artifact['contract_version']}`",
        f"- **Artifact Identity**: `{artifact['artifact_identity']}`",
        f"- **Total Network Requests**: `{artifact['hard_request_budget']['total_requests']}` (Ceiling: 7)",
        "",
        "## Request Budget & Actual Counts",
        "",
        "| Ticker | Budget | Actual Requests | Status After Enrichment | Candidate Host |",
        "|---|---|---|---|---|",
    ]
    for rec in artifact["records"]:
        t = rec["ticker"]
        b = artifact["hard_request_budget"]["per_ticker_budget"][t]
        actual = artifact["hard_request_budget"]["actual_network_requests"][t]
        st = rec["prospective_owner_review_status"]
        host = rec["candidate_host"]
        lines.append(f"| **{t}** | {b} | {actual} | `{st}` | `{host}` |")

    lines.extend([
        "",
        "## Enriched Records Detail",
        "",
    ])
    for rec in artifact["records"]:
        lines.extend([
            f"### {rec['ticker']} — {rec['expected_issuer_identity']}",
            f"- **Requested URL**: `{rec['requested_url']}`",
            f"- **Requested Host**: `{rec['requested_host']}`",
            f"- **Final URL**: `{rec['final_url']}`",
            f"- **Final Host**: `{rec['final_host']}`",
            f"- **Redirect Authority Verdict**: `{rec['redirect_authority_verdict']}`",
            f"- **Retained File**: `{rec['retained_file_path']}`",
            f"- **SHA-256**: `{rec['retained_sha256']}` ({rec['content_bytes_length']} bytes)",
            f"- **Review Status**: `{rec['prospective_owner_review_status']}`",
            f"- **Identity Verdict**: `{rec['identity_match_verdict']}`",
            f"- **Observed Identity**: `{rec['observed_identity']}`",
            f"- **Evidence Types**: `{', '.join(rec['evidence_types'])}`",
            f"- **Extracted Spans**:",
        ])
        for span in rec["extracted_identity_evidence"]:
            lines.append(f"  - `[{span['evidence_type']}]` \"{span['span']}\" (source: `{span['source']}`)")
        lines.append("")

    lines.extend([
        "## Governed Registry Candidates Proposed (Pending Owner Promotion)",
        "",
    ])
    for cand in artifact["governed_registry_candidates_proposed"]:
        lines.append(
            f"- **{cand['ticker']}**: `{cand['candidate_host']}` ({cand['candidate_url']}) -> `{cand['activation_recommendation']}`"
        )

    lines.extend([
        "",
        "## Authority & Governance Boundaries",
        "- `registry_mutated`: `false` (`config/official_source_registry.json` unmutated)",
        "- `financial_documents_acquired`: `0`",
        "- `financial_facts_created`: `0`",
        "- `fundamental_readiness_mutated`: `false`",
        "- `historical_evidence_preserved`: `true` (AAT `tienson.vn` preserved as `IDENTITY_CONFLICT`)",
    ])
    return "\n".join(lines) + "\n"


def run(live: bool = True) -> dict:
    artifact = execute_bounded_enrichment(live_network=live, evidence_dir=ENRICHMENT_EVIDENCE_DIR)
    OPERATIONS_REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_ARTIFACT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUTPUT_SUMMARY.write_text(_generate_summary_markdown(artifact), encoding="utf-8")
    return artifact


if __name__ == "__main__":
    live_flag = "--offline" not in sys.argv
    res = run(live=live_flag)
    print(json.dumps(res, ensure_ascii=False, indent=2))
