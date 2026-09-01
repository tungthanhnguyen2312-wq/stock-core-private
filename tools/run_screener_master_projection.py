"""Materialize screener_master_projection/v1 from retained governed artifacts. No network."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from financial_analysis_product_projection import build_product_projection  # noqa: E402
from screener_master_projection import (  # noqa: E402
    CONTRACT_VERSION, build_projection, js_fallback, load_screen_snapshot_rows, load_vci_industry_labels,
)

OUT = ROOT / "operations-review" / "screener-master-projection-v1-20260901"
SEARCH_ROOTS = [
    ROOT,
    ROOT / "operations-review",
    Path(r"C:\Projects\StockLookup\dashboard-runtime"),
    Path(r"C:\Projects\StockLookup\stock-core-private"),
    Path(r"C:\Projects\StockLookup\worktrees\stock-core-working-capital-short-term-liquidity-v1-20260901"),
    Path(r"C:\Projects\StockLookup\worktrees\stock-core-financial-entity-classification-scaleout-v1-20260901"),
    Path(r"C:\Projects\StockLookup\worktrees\stock-core-financial-analysis-v2-scaleout-v1-20260901"),
    Path(r"C:\Projects\StockLookup\worktrees\stock-core-financial-analysis-v2-product-ai-bundle-integration-v1-20260901"),
    Path(r"C:\Projects\StockLookup\worktrees\stock-core-investment-decision-workspace-v1-20260831"),
    Path(r"C:\Projects\StockLookup\worktrees\stock-core-dashboard-surface-convergence-v1-20260831"),
]


def resolve(*relative: str) -> Path | None:
    for root in SEARCH_ROOTS:
        for item in relative:
            path = Path(item)
            candidate = path if path.is_absolute() else root / item
            if candidate.is_file():
                return candidate
    return None


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screen-snapshot", type=Path, default=None)
    parser.add_argument("--workspace", type=Path, default=None)
    parser.add_argument("--financial-v2", type=Path, default=None)
    parser.add_argument("--vci-industry", type=Path, default=None)
    parser.add_argument("--official-universe", type=Path, default=None)
    parser.add_argument("--requested-at", default="2026-09-01T00:00:00+07:00")
    parser.add_argument("--output-dir", type=Path, default=OUT)
    args = parser.parse_args()

    snapshot_path = args.screen_snapshot or resolve(
        "screen_snapshot.csv",
        "operations-review/canonical-dashboard-runtime-release/screen_snapshot.csv",
    )
    if snapshot_path is None:
        raise FileNotFoundError("CANONICAL_SCREEN_SNAPSHOT_NOT_FOUND")
    rows = load_screen_snapshot_rows(snapshot_path)

    workspace_path = args.workspace or resolve(
        "operations-review/investment-decision-workspace-v1-20260831/investment_decision_workspace_artifact.json",
        "operations-review/financial-analysis-v2-product-ai-bundle-integration-v1-20260901/investment_decision_workspace_artifact.json",
        "data/investment_decision_workspace.json",
        "investment_decision_workspace_artifact.json",
    )
    workspace = load_json(workspace_path) if workspace_path else None

    financial_path = args.financial_v2 or resolve(
        "operations-review/market-wide-working-capital-short-term-liquidity-v1-20260901/financial_analysis_v2_market_wide_after.json",
        "operations-review/market-wide-financial-analysis-v2-scaleout-v1-20260901/financial_analysis_context_v2_market_wide.json",
        "operations-review/financial-analysis-v2-product-ai-bundle-integration-v1-20260901/financial_analysis_product_integration.json",
        "financial_analysis_product_integration.json",
    )
    financial_v2 = None
    if financial_path is not None:
        loaded = load_json(financial_path)
        if loaded.get("contract_version") == "financial_analysis_context/v2":
            financial_v2 = build_product_projection(
                financial_context=loaded,
                product_tickers=[row.get("ticker") for row in rows],
                requested_at=args.requested_at,
            )
        else:
            financial_v2 = loaded

    industry_path = args.vci_industry or resolve(
        "registry_snapshots/metadata/vnstock_metadata_snapshot_20260728T122548Z_16fe54ee3497.jsonl",
    )
    industry = load_vci_industry_labels(industry_path) if industry_path else {}

    official_path = args.official_universe or resolve(
        "current_official_market_universe_artifact.json",
        "operations-review/current-official-market-universe-integration-v1-20260824/artifact.json",
    )
    official = load_json(official_path) if official_path else None

    artifact = build_projection(
        snapshot_rows=rows,
        requested_at=args.requested_at,
        snapshot_identity=f"canonical_screen_snapshot:{snapshot_path.name}",
        workspace=workspace,
        financial_v2=financial_v2,
        industry_by_ticker=industry,
        official_universe=official,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "screener_master_projection.json"
    js_path = args.output_dir / "screener_master_projection.js"
    json_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    js_path.write_text(js_fallback(artifact), encoding="utf-8")
    validation = {
        "milestone": artifact["milestone"],
        "contract_version": CONTRACT_VERSION,
        "as_of_session": artifact["as_of_session"],
        "artifact_identity": artifact["artifact_identity"],
        "coverage": artifact["coverage"],
        "inputs_used": {
            "screen_snapshot": str(snapshot_path),
            "workspace": str(workspace_path) if workspace_path else None,
            "financial_v2": str(financial_path) if financial_path else None,
            "vci_industry": str(industry_path) if industry_path else None,
            "official_universe": str(official_path) if official_path else None,
        },
        "outputs": {"json": str(json_path), "js": str(js_path)},
    }
    (args.output_dir / "validation_artifact.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    print(json.dumps({
        "artifact_identity": artifact["artifact_identity"],
        "as_of_session": artifact["as_of_session"],
        "ticker_denominator": artifact["coverage"]["ticker_denominator"],
        "price_available_count": artifact["coverage"]["price_available_count"],
        "hnx_listed_display_hnx_count": artifact["coverage"]["hnx_listed_display_hnx_count"],
        "sector_available_count": artifact["coverage"]["sector_available_count"],
        "naked_required_null_count": artifact["coverage"]["naked_required_null_count"],
        "json": str(json_path),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
