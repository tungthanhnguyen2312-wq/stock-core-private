"""CLI: derive and retain the MARKET_PRICE_VOLUME_BASIS_QUALIFICATION_V1 fitness matrix.

Pure consolidation over already-authoritative modules (see
``market_price_volume_basis_authority.py``'s module docstring). This tool makes no network
call, mutates no runtime database, and promotes no authority: it only assembles, validates, and
retains the deterministic matrix under ``operations-review/``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import market_price_volume_basis_authority as basis_authority  # noqa: E402

DEFAULT_OUTPUT_DIR = ROOT / "operations-review" / "market-price-volume-basis-qualification-v1-20260822"


def _render_report(matrix: dict) -> str:
    lines = [
        "# Market Price/Volume Basis Qualification V1",
        "",
        f"- contract_version: `{matrix['contract_version']}`",
        f"- artifact_identity: `{matrix['artifact_identity']}`",
        f"- capability rows: {len(matrix['capability_rows'])}",
        "",
        "## Global invariants",
        "",
    ]
    for key, value in sorted(matrix["global_invariants"].items()):
        lines.append(f"- `{key}` = `{value}`")
    lines.append("")
    lines.append("## Capability fitness matrix")
    lines.append("")
    lines.append("| capability_id | domain | " + " | ".join(matrix["use_cases"]) + " |")
    lines.append("|---|---|" + "---|" * len(matrix["use_cases"]))
    for row in matrix["capability_rows"]:
        cells = " | ".join(row["fitness"][use]["state"] for use in matrix["use_cases"])
        lines.append(f"| {row['capability_id']} | {row['domain']} | {cells} |")
    lines.append("")
    lines.append("## Cross-cutting impact")
    lines.append("")
    lines.append(f"- current valuation price input: `{matrix['current_valuation_price_input_impact']['price_input_status']}`")
    lines.append(f"- liquidity/sizing newly unlocked: `{matrix['liquidity_and_sizing_impact']['sizing_or_execution_capacity_newly_unlocked']}`")
    lines.append(f"- PIT/backtest readiness changed: `{matrix['pit_and_backtest_impact']['pit_readiness_changed']}` / `{matrix['pit_and_backtest_impact']['backtest_readiness_changed']}`")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    matrix = basis_authority.build_matrix()
    basis_authority.assert_registry_fail_closed(matrix)

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = output_dir / "market_price_volume_basis_authority_artifact.json"
    report_path = output_dir / "market_price_volume_basis_authority_report.md"
    artifact_path.write_text(json.dumps(matrix, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(_render_report(matrix), encoding="utf-8")

    print(json.dumps({
        "artifact_identity": matrix["artifact_identity"],
        "artifact_path": str(artifact_path),
        "report_path": str(report_path),
        "capability_rows": len(matrix["capability_rows"]),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
