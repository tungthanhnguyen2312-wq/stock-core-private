"""PROVIDER_FINANCIAL_SEMANTIC_BASIS_QUALIFICATION_V1.

Follow-on inside the existing current-fundamental / current-valuation evidence lane (see
``provider_financial_semantic_basis.py`` for the full evidentiary argument). Does not acquire
broad new financial coverage, does not build a new valuation engine, and does not promote provider
data to official authority.

Reuses, unmodified:
  - the wide fundamental/p3f10/p3f13 artifacts from the immediately preceding
    ``current-financial-fact-coverage-recovery-and-scaleout-v1-20260827`` milestone (raw
    ``data_bctc`` payloads are unchanged since 2026-08-03 -- 4,195 payloads either way -- so
    reusing them is not a data hunt, it is the same retained evidence this milestone read-only
    inspects);
  - ``market_wide_current_valuation_input_scaleout.build_current_valuation_artifact`` (unmodified);
  - ``canonical_fact_store``/``canonical_financial_facts`` (Layer 3), read-only, against
    ``dashboard-runtime`` (no write, no network -- see docs/market_wide_financial_normalization_contract.md).

Writes only to a new, non-frozen ``operations-review`` directory.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import financial_fact_coverage_recovery as ffcr
import market_wide_current_fundamental_research as mwcfr
import provider_financial_semantic_basis as pfsb
from derive_financial_fact_coverage_recovery_v1 import (
    DEFAULT_P3F5, DEFAULT_PRICE_SNAPSHOT, DEFAULT_SHARE_AUTHORITY, NARROW_FUNDAMENTAL,
    build_valuation,
)
from field_temporal_contract import stable_id
from p3f10_fundamental_evidence_scaleout import DEFAULT_P3E

OPS = ROOT / "operations-review"
PRIOR_OUTPUT_DIR = OPS / "current-financial-fact-coverage-recovery-and-scaleout-v1-20260827"
OUTPUT_DIR = OPS / "provider-financial-semantic-basis-qualification-v1-20260827"

DEFAULT_RUNTIME_ROOT = ROOT.parent / "dashboard-runtime"
DEFAULT_OFFICIAL_UNIVERSE = OPS / "current-official-market-universe-integration-v1-20260824" / "current_official_market_universe_artifact.json"


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_registry_and_evidence(runtime_root: Path) -> tuple[dict, dict]:
    """Phase 3 + 5 + 7-evidence: read-only against `runtime_root`, bounded to the tickers that
    carry an official citation (see `provider_financial_semantic_basis.
    load_provider_exact_research_evidence` docstring for why that bound is exact, not a shortcut).
    """
    import canonical_fact_store as store

    citations = store.load_official_citations(runtime_root)
    tickers = sorted({key[0] for key in citations})
    profiles = store.load_entity_profiles(ROOT / "config" / "ticker_entity_profiles.csv")
    facts_by_ticker = {
        ticker: store.build_ticker_facts(runtime_root, ticker, profiles=profiles, official_citations=citations)["facts"]
        for ticker in tickers
    }
    reconciliation = pfsb.reconcile_official_anchors(facts_by_ticker)
    registry = pfsb.build_semantic_basis_registry(reconciliation)
    evidence = pfsb.load_provider_exact_research_evidence(runtime_root, registry=registry)
    return registry, evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--official-universe", type=Path, default=DEFAULT_OFFICIAL_UNIVERSE)
    parser.add_argument("--prior-output-dir", type=Path, default=PRIOR_OUTPUT_DIR)
    args = parser.parse_args()

    fundamental_before = _read(args.prior_output_dir / "market_wide_current_fundamental_research_wide_artifact.json")
    p3f13_before = _read(args.prior_output_dir / "p3f13_wide_artifact.json")
    inventory_before = _read(args.prior_output_dir / "financial_identity_inventory.json")
    valuation_before = _read(args.prior_output_dir / "market_wide_current_valuation_artifact.json")

    registry, provider_exact_evidence = build_registry_and_evidence(args.runtime_root)

    canonical_presence = ffcr.load_canonical_metric_presence(mwcfr.DEFAULT_CANONICAL_FACTS_ROOT)
    official_facts = ffcr.load_official_facts_by_ticker(p3f13_before)
    inventory_after = ffcr.build_financial_identity_inventory(
        fundamental_before, canonical_presence, official_facts,
        provider_exact_research_evidence_by_ticker=provider_exact_evidence,
    )
    if not inventory_after["residual_zero"]:
        raise ValueError(f"IDENTITY_INVENTORY_RESIDUAL_NONZERO:{inventory_after['residual']}")

    # Fundamental artifact itself is untouched by this milestone (no upstream module changed), so
    # the valuation rerun is a verification that this is really true, not a new computation path.
    official = _read(args.official_universe)
    p3e = _read(DEFAULT_P3E)
    p3f5 = _read(DEFAULT_P3F5)
    price = _read(DEFAULT_PRICE_SNAPSHOT)
    share_authority = _read(DEFAULT_SHARE_AUTHORITY)
    valuation_after = build_valuation(
        fundamental_artifact=fundamental_before, price=price, p3f5=p3f5, official=official,
        p3e=p3e, share_authority=share_authority,
    )
    valuation_unchanged = valuation_after.get("artifact_sha256") == valuation_before.get("artifact_sha256")

    state_diff = {
        state: {
            "before": inventory_before["state_counts"].get(state, 0),
            "after": inventory_after["state_counts"].get(state, 0),
        }
        for state in sorted(set(inventory_before["state_counts"]) | set(inventory_after["state_counts"]))
    }
    changed_cells = [
        {"ticker": ticker, "identity": cell_after["identity"],
         "before": cell_before["state"], "after": cell_after["state"]}
        for ticker in inventory_after["cells"]
        for cell_before, cell_after in zip(inventory_before["cells"].get(ticker, []), inventory_after["cells"][ticker])
        if cell_before["state"] != cell_after["state"]
    ]

    report = {
        "contract_version": pfsb.CONTRACT_VERSION,
        "milestone": "PROVIDER_FINANCIAL_SEMANTIC_BASIS_QUALIFICATION_V1",
        "semantic_basis_registry_identity": registry.get("artifact_identity"),
        "semantic_basis_verdict_counts": registry["verdict_counts"],
        "any_shape_absolute_research_qualified": registry["any_shape_absolute_research_qualified"],
        "provider_exact_research_evidence_ticker_count": len(provider_exact_evidence),
        "provider_exact_research_evidence_tickers": sorted(provider_exact_evidence),
        "identity_inventory_state_counts_before_after": state_diff,
        "identity_inventory_residual_before": inventory_before["residual"],
        "identity_inventory_residual_after": inventory_after["residual"],
        "changed_cells": changed_cells,
        "changed_cell_count": len(changed_cells),
        "valuation_artifact_identity_before": valuation_before.get("artifact_identity"),
        "valuation_artifact_identity_after": valuation_after.get("artifact_identity"),
        "valuation_unchanged": valuation_unchanged,
        "valuation_metric_research_usable_counts_before": valuation_before.get("coverage", {}).get("metric_research_usable_counts"),
        "valuation_metric_research_usable_counts_after": valuation_after.get("coverage", {}).get("metric_research_usable_counts"),
        "valuation_metric_ready_counts_before": valuation_before.get("coverage", {}).get("metric_ready_counts"),
        "valuation_metric_ready_counts_after": valuation_after.get("coverage", {}).get("metric_ready_counts"),
        "value_strategy_eligible_before": valuation_before.get("value_strategy_readiness", {}).get("eligible"),
        "value_strategy_eligible_after": valuation_after.get("value_strategy_readiness", {}).get("eligible"),
        "authority_boundary": {
            "new_provider_added": False,
            "new_official_evidence_acquired": False,
            "official_authority_promoted": False,
            "value_strategy_activated": valuation_after.get("value_strategy_readiness", {}).get("eligible", 0) > 0,
            "frozen_prior_artifacts_rewritten": False,
        },
    }
    report["report_sha256"] = stable_id(report)

    _write(OUTPUT_DIR / "provider_financial_semantic_basis_registry.json", registry)
    _write(OUTPUT_DIR / "provider_exact_research_evidence.json", provider_exact_evidence)
    _write(OUTPUT_DIR / "financial_identity_inventory_after.json", inventory_after)
    _write(OUTPUT_DIR / "market_wide_current_valuation_artifact_after.json", valuation_after)
    _write(OUTPUT_DIR / "semantic_basis_qualification_report.json", report)

    print(json.dumps({
        "semantic_basis_verdict_counts": report["semantic_basis_verdict_counts"],
        "any_shape_absolute_research_qualified": report["any_shape_absolute_research_qualified"],
        "identity_inventory_state_counts_before_after": report["identity_inventory_state_counts_before_after"],
        "changed_cell_count": report["changed_cell_count"],
        "valuation_unchanged": report["valuation_unchanged"],
        "valuation_metric_research_usable_counts_after": report["valuation_metric_research_usable_counts_after"],
        "value_strategy_eligible_after": report["value_strategy_eligible_after"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
