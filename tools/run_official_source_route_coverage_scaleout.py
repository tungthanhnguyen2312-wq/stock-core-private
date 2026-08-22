"""Run the bounded, non-activating official-source route coverage scaleout."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from official_financial_source_route_discovery import LEGAL_IDENTITY_HINTS, STATIC_ISSUER_ROUTE_HINTS
from official_source_route_coverage import build_artifact, inspect_seed, requests_fetcher

OUTPUT = ROOT / "operations-review" / "official-source-route-evidence-coverage-scaleout-v1-20260822" / "official_source_route_coverage_artifact.json"
# These are the seven unapproved, exact repository candidates from the prior closed-world
# Wave-2 mapping.  No domain is constructed from a ticker and no other URL is requested.
TARGETS = ("AAH", "AAN", "AAS", "AAV", "ABB", "ACC", "VIC")


def baseline() -> dict:
    return {
        "research_universe_2026_08_20": 523,
        "separate_shadow_snapshot_universe_2026_08_21": 524,
        "universe_reconciliation": {
            "relationship": "distinct_session_scoped_empirical_shadow_cohorts_not_subset_exclusion",
            "retained_intersection": 521,
            "entered_in_2026_08_21_snapshot": ["HMS", "VPS", "VTC"],
            "exited_from_2026_08_20_cohort": ["BRS", "CCS"],
        },
        "approved_issuer_routes": 22,
        "ownership_proven_unapproved_routes": 0,
        "ambiguous_routes": 2,
        "no_usable_route": 510,
        "supported_source_families": ["issuer_ir", "exchange_disclosure", "vsdc_notice"],
        "evidence": [
            "operations-review/official-financial-evidence-scaleout-wave2-20260821/wave2_official_financial_evidence_scaleout_artifact.json",
            "operations-review/official-source-registry-owner-promotion-v1-20260821/official_source_registry_owner_promotion_artifact.json",
            "operations-review/prospective-route-ownership-review-v1-20260821/prospective_route_ownership_review_artifact.json",
        ],
    }


def run(*, fetcher=requests_fetcher, output: Path = OUTPUT, replay: bool = False) -> dict:
    if replay:
        if not output.is_file():
            raise ValueError("replay_requires_retained_route_artifact")
        retained = json.loads(output.read_text(encoding="utf-8"))
        artifact = build_artifact(baseline=baseline(), routes=retained["routes"])
    else:
        routes = []
        for ticker in TARGETS:
            routes.append(inspect_seed({"ticker": ticker, "issuer_id": LEGAL_IDENTITY_HINTS[ticker]["legal_name"], "locator": STATIC_ISSUER_ROUTE_HINTS[ticker]}, fetcher=fetcher))
        artifact = build_artifact(baseline=baseline(), routes=routes)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return artifact


if __name__ == "__main__":
    result = run(replay="--replay" in sys.argv)
    print(json.dumps({"artifact_identity": result["artifact_identity"], "lifecycle_gate_counts": result["lifecycle_gate_counts"]}, ensure_ascii=False))
