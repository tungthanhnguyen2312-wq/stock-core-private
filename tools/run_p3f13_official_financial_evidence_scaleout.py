"""Operational runner for P3-F13: Generic Official Financial Evidence Operational Scale-Out."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from p3f13_official_financial_evidence_scaleout import execute

DEFAULT_OUTPUT_DIR = ROOT / "operations-review" / "p3f13-official-financial-evidence-scaleout-20260820"
DEFAULT_ARTIFACT = DEFAULT_OUTPUT_DIR / "p3f13_official_financial_evidence_scaleout_artifact.json"
DEFAULT_REPORT = DEFAULT_OUTPUT_DIR / "p3f13_official_financial_evidence_scaleout_report.md"


def generate_markdown_report(artifact: dict[str, Any]) -> str:
    cmp = artifact["before_after_comparison"]
    lines = [
        "# P3-F13 — Generic Official Financial Evidence Operational Scale-Out Report",
        "",
        f"- **Artifact Identity**: `{artifact['artifact_identity']}`",
        f"- **Scaleout Gate**: `{artifact['scaleout_gate']}`",
        f"- **Verdict**: `{artifact['verdict']}`",
        f"- **Next Gate**: `{artifact['next_gate']}`",
        "",
        "## 1. Target Cohort & Discovery Execution",
        "",
        f"- **Total Empirical Active Cohort**: `{artifact['cohort_identity']['total_cohort_count']}`",
        f"- **Target Blocked Cohort Attempted**: `{artifact['cohort_identity']['target_blocked_cohort_count']}`",
        f"- **Unattempted Without Explicit Disposition**: `{artifact['acquisition_dispositions_summary']['unattempted_without_explicit_disposition']}`",
        f"- **Disposition Reconciliation OK**: `{artifact['acquisition_dispositions_summary']['disposition_reconciliation_ok']}`",
        "",
        "### Disposition Breakdown",
        "",
        "| Disposition | Count | Meaning |",
        "|---|---:|---|",
    ]
    for disp, cnt in artifact["acquisition_dispositions_summary"]["disposition_counts"].items():
        meaning = "Filing already retained in governed official evidence repository" if disp == "FILING_ALREADY_RETAINED" else "No approved issuer IR host or exchange disclosure route in official source registry"
        lines.append(f"| `{disp}` | {cnt} | {meaning} |")

    lines.extend([
        "",
        "## 2. Fundamental Coverage Before & After",
        "",
        "| Metric / Dimension | Before (P3-E baseline) | After (P3-F13 scale-out) | Delta |",
        "|---|---:|---:|---:|",
        f"| Qualified Official Issuers | {cmp['official_filings_acquired_or_retained']['before']} | {cmp['official_filings_acquired_or_retained']['after']} | +{cmp['official_filings_acquired_or_retained']['delta']} |",
        f"| Metadata-Qualified Issuers | {cmp['metadata_qualified_issuers']['before']} | {cmp['metadata_qualified_issuers']['after']} | +{cmp['metadata_qualified_issuers']['delta']} |",
        f"| Value-Qualified Issuers | {cmp['value_qualified_issuers']['before']} | {cmp['value_qualified_issuers']['after']} | +{cmp['value_qualified_issuers']['delta']} |",
        f"| Canonical Exact-Qualified Facts | {cmp['canonical_exact_qualified_facts']['before']} | {cmp['canonical_exact_qualified_facts']['after']} | +{cmp['canonical_exact_qualified_facts']['delta']} |",
        f"| Exact-Qualified P3-B Metrics | {cmp['exact_qualified_metrics']['before']} | {cmp['exact_qualified_metrics']['after']} | +{cmp['exact_qualified_metrics']['delta']} |",
        f"| Derived Proxy P3-B Metrics | {cmp['derived_proxies']['before']} | {cmp['derived_proxies']['after']} | +{cmp['derived_proxies']['delta']} |",
        f"| Missing / Data Gap Metrics | {cmp['missing_metrics']['before']} | {cmp['missing_metrics']['after']} | +{cmp['missing_metrics']['delta']} |",
        "",
        "### Issuer Fundamental Readiness",
        "",
        f"- **COMPLETE**: `{cmp['fundamental_readiness_status']['after']['COMPLETE']}`",
        f"- **PARTIAL**: `{cmp['fundamental_readiness_status']['after']['PARTIAL']}` ({', '.join(artifact['newly_qualified_issuers'])} joined)",
        f"- **BLOCKED**: `{cmp['fundamental_readiness_status']['after']['BLOCKED']}`",
        "",
        "## 3. Root Blocker Distribution",
        "",
        "| Root Cause | Affected Instruments | Analytical Description |",
        "|---|---:|---|",
    ] + [
        f"| `{r['root_cause']}` | {r['affected_instruments']} | {r['description']} |"
        for r in artifact["root_blocker_distribution"]
    ] + [
        "",
        "## 4. Authority Boundaries",
        "",
        f"- `new_provider_added`: `{artifact['authority_boundaries']['new_provider_added']}`",
        f"- `source_authority_promoted`: `{artifact['authority_boundaries']['source_authority_promoted']}`",
        f"- `canonical_store_mutated`: `{artifact['authority_boundaries']['canonical_store_mutated']}`",
        f"- `runtime_database_mutated`: `{artifact['authority_boundaries']['runtime_database_mutated']}`",
        f"- `p3g_started`: `{artifact['authority_boundaries']['p3g_started']}`",
        f"- `ticker_specific_branch_audit`: `{artifact['ticker_specific_branch_audit']['status']}`",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    artifact = execute()

    artifact_path = args.output_dir / "p3f13_official_financial_evidence_scaleout_artifact.json"
    artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report_path = args.output_dir / "p3f13_official_financial_evidence_scaleout_report.md"
    report_path.write_text(generate_markdown_report(artifact), encoding="utf-8")

    print(f"Generated P3-F13 artifact: {artifact['artifact_identity']}")
    print(f"Artifact path: {artifact_path}")
    print(f"Report path: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
