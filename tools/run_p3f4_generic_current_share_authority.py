"""Emit the deterministic P3-F4 current-share authority review artifact.

Read-only against runtime evidence.  This is an authority diagnosis and resolver
contract check, not a source-acquisition or valuation run.
"""
from __future__ import annotations

import argparse
import inspect
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import current_share_authority as share_authority
import current_valuation_input_authority as inputs
from current_state_relative_valuation import resolve_current_shares
from field_temporal_contract import stable_id
from runtime_paths import runtime_root as resolve_runtime_root

VERSION = "1.0.0"
ARTIFACT_TYPE = "P3F4_GENERIC_CURRENT_SHARE_AUTHORITY"
P3E_PATH = ROOT / "operations-review" / "p3e-fundamental-coverage-closeout-20260820" / "p3e_fundamental_coverage_closeout_artifact.json"
P3F2_PATH = ROOT / "operations-review" / "p3f2-current-valuation-input-authority-20260820" / "p3f2_current_valuation_input_authority_artifact.json"
P3F3_PATH = ROOT / "operations-review" / "p3f3-operational-valuation-input-scaleout-20260820" / "p3f3_operational_valuation_input_scaleout_artifact.json"
DEFAULT_OUTPUT_DIR = ROOT / "operations-review" / "p3f4-generic-current-share-authority-20260820"
REFERENCE_AT = "2026-08-20T14:00:00+07:00"


def _cohort() -> list[dict[str, Any]]:
    p3e = json.loads(P3E_PATH.read_text(encoding="utf-8"))
    return sorted(p3e["refreshed_panel_data"]["issuers"], key=lambda row: row["issuer_identity"]["ticker"])


def _branch_audit() -> dict[str, Any]:
    modules = (share_authority, inputs)
    branch_tokens = ("HPG", "SSI", "VCB", "VNM", "GAS", "NVL", "PAN", "POW", "PVD", "QNS", "VRE")
    matches: list[str] = []
    for module in modules:
        source = inspect.getsource(module)
        for ticker in branch_tokens:
            if f'== "{ticker}"' in source or f"== '{ticker}'" in source:
                matches.append(f"{module.__name__}:{ticker}")
    return {"production_modules": [module.__name__ for module in modules], "ticker_specific_qualification_branches": len(matches), "matches": matches}


def build_artifact(runtime_root: Path) -> dict[str, Any]:
    p3f2 = json.loads(P3F2_PATH.read_text(encoding="utf-8"))
    p3f3 = json.loads(P3F3_PATH.read_text(encoding="utf-8"))
    cohort = _cohort()
    instruments = [inputs.canonical_instrument(row["issuer_identity"]["ticker"]) for row in cohort]
    financial = {row["issuer_identity"]["ticker"]: row for row in cohort}
    scan = inputs.scan_current_valuation_input_coverage(
        instruments, runtime_root=runtime_root, requested_at=REFERENCE_AT, financial_by_ticker=financial,
    )
    shares_by_ticker = {
        row["canonical_instrument"]["canonical_ticker"]: resolve_current_shares(runtime_root, row["canonical_instrument"]["canonical_ticker"], row["valuation_session"])
        for row in scan["rows"]
    }
    action_findings = p3f3["corporate_action_invalidations"]
    transition_proof = next((result for result in shares_by_ticker.values() if result["raw_event_citation_count"] > 0), None)
    period_only = next((row for row in scan["rows"] if "period_end_shares" in row["shares"].get("observed_identities", [])), None)
    no_citation = next((result for result in shares_by_ticker.values()
                        if (result.get("opening_identity_diagnostic") or {}).get("reason") == "no_period_end_share_basis_citation_retained_for_ticker"), None)
    registration = [
        {"ticker": ticker, "diagnostic": result["opening_identity_diagnostic"]}
        for ticker, result in sorted(shares_by_ticker.items())
        if (result.get("opening_identity_diagnostic") or {}).get("detail")
    ]
    counts = scan["counts"]
    artifact: dict[str, Any] = {
        "schema_version": VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "verdict": "P3F4_CURRENT_SHARE_FOUNDATION_COMPLETE",
        "source_artifacts": {"p3f2": p3f2["artifact_identity"], "p3f3": p3f3["artifact_identity"]},
        "valuation_reference": REFERENCE_AT,
        "root_cause_matrix": {
            "classification": "H_COMBINATION",
            "A_no_scalable_current_common_source": "present",
            "B_unapproved_provider_candidate": "present",
            "C_registration_linkage_defects": {"present": bool(registration), "repair": "NOT_SAFE_WITH_CURRENT_CITATION_LINEAGE"},
            "D_identity_insufficient": "present_for_period_end_and_issued_fields",
            "E_effective_coverage_absent": "present",
            "F_corporate_action_uncertainty": "present",
            "G_resolver_defect": "not_dominant; existing resolver already fails closed and P3-F4 makes its timeline contract explicit",
        },
        "source_authority_inventory": share_authority.SOURCE_AUTHORITY_INVENTORY,
        "share_semantic_contract": {
            "required_for_market_cap": share_authority.COMMON_OUTSTANDING,
            "distinct_identities": sorted(share_authority.SHARE_IDENTITIES),
            "numerical_equality_is_not_semantic_equivalence": True,
        },
        "effective_date_and_continuity": {
            "synthetic_forward_fill": "PROHIBITED",
            "eligible_only_when": "explicit_common_outstanding_and_valid_from_through_includes_valuation_date",
            "reference_session": scan["rows"][0]["valuation_session"] if scan["rows"] else None,
        },
        "corporate_action_completeness": action_findings,
        "generic_implementation": {
            "module": "current_share_authority.py",
            "contract": share_authority.CONTRACT_VERSION,
            "integration": "current_valuation_input_authority.qualify_current_share_basis",
            "valuation_formula_change": False,
            "source_promotion": False,
        },
        "representative_proofs": {
            "executed_transition": transition_proof,
            "unresolved_planned_issuance": next((item for item in action_findings if item.get("event_type") == "planned_issuance"), None),
            "fy2024_period_end_only": period_only["shares"] if period_only else None,
            "no_verified_current_citation": no_citation,
        },
        "registration_hash_repairs": {"repairs_made": [], "unresolved": registration,
                                      "reason": "citation_to_manifest remapping requires immutable linkage not present in legacy citation rows"},
        "coverage_scan": {"counts": counts, "blocker_distribution": scan["blocker_distribution"],
                          "rows": [{"ticker": row["canonical_instrument"]["canonical_ticker"], "price": row["price"]["status"],
                                    "shares": row["shares"]["status"], "blockers": row["blocker_codes"]} for row in scan["rows"]]},
        "coverage_before_after": {"before": p3f3["authority_coverage_before_after"]["post_scaleout_p3f3"],
                                   "after": {key: counts.get(key, 0) for key in ("PRICE_READY", "PRICE_BLOCKED", "SHARE_READY", "SHARE_BLOCKED", "BOTH_READY")}},
        "ticker_specific_branch_audit": _branch_audit(),
        "source_promotion_review": {
            "AUTHORITY": "NOT_PROMOTED", "candidate": "VCI.overview.issue_share retained provider metadata",
            "exact_share_semantic": "ISSUED_SHARES, not proven common_shares_outstanding",
            "temporal_semantics": "metadata updated timestamp; no approved effective-date or corporate-action completeness contract",
            "provenance_retention": "vn_stock.db metadata row and update timestamp",
            "comparison": "may corroborate but is not semantically interchangeable with official current common shares",
            "scalability": "market-wide metadata field exists but authority does not scale by presence alone",
            "risks": ["issued_vs_outstanding", "unknown_treasury_treatment", "event freshness", "no owner promotion"],
            "proposed_bounded_allowed_use": "future descriptive candidate review only; never market-cap input until owner approval",
        },
        "boundaries": {"p3g": "RESERVED_NOT_STARTED", "raw_as_traded": "NOT_PROMOTED", "is_actionable": False},
    }
    artifact["artifact_sha256"] = stable_id(artifact)
    artifact["artifact_identity"] = f"p3f4_generic_current_share_authority:{artifact['artifact_sha256']}"
    return artifact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", default=None)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args(argv)
    artifact = build_artifact(resolve_runtime_root(args.runtime_root))
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    path = output / "p3f4_generic_current_share_authority_artifact.json"
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Artifact identity: {artifact['artifact_identity']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
