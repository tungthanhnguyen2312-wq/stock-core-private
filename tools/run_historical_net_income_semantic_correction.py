"""Write the public-safe historical net-income semantic correction overlay (no network)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from financial_evidence_currency_refresh import financial_v2_pin_decision  # noqa: E402
from historical_net_income_semantic_correction import (  # noqa: E402
    CLASS_A,
    CONTRACT_VERSION,
    FINANCIAL_V2_PIN,
    MILESTONE_ID,
    PARENT_ATTRIBUTABLE_INCOME_REQUIRED,
    PUBLIC_CORRECTIONS,
    PUBLIC_DIR,
    PUBLIC_FACTS,
    PUBLIC_REPORT,
    TOTAL_NET_INCOME_REQUIRED,
    build_all_correction_records,
    build_public_report,
    class_a_outcome,
    current_authority_fact_rows,
    render_jsonl,
)


def _consumer_impact() -> list[dict[str, Any]]:
    rows = []
    for entry in CLASS_A:
        outcome = class_a_outcome(entry)
        total = outcome["net_income"]
        parent = outcome["attributable_net_income"]
        rows.append({
            "ticker": entry["ticker"], "reporting_period": entry["reporting_period"],
            "old_metric": "net_income", "old_value": entry["wrong"]["value"],
            "new_total_net_income": total["value"], "new_attributable_net_income": parent["value"],
            "fundamental_readiness": {
                "classification": TOTAL_NET_INCOME_REQUIRED,
                "uses": "qualified line-60 net_income" if total["available"] else "BLOCKED_TOTAL_NET_INCOME_UNAVAILABLE",
                "delta_reason": "corporate formulas consume canonical net_income (total profit after tax)",
            },
            "valuation_pe": {
                "classification": TOTAL_NET_INCOME_REQUIRED,
                "uses": "qualified line-60 net_income" if total["available"] else "BLOCKED_TOTAL_NET_INCOME_UNAVAILABLE",
                "delta_reason": "EARNINGS_IDENTITY_BY_ENTITY corporate = net_income; parent vs total kept distinct",
            },
            "parent_attributable_consumer": {
                "classification": PARENT_ATTRIBUTABLE_INCOME_REQUIRED,
                "uses": "qualified line-61 attributable_net_income" if parent["available"] else "UNAVAILABLE",
            },
        })
    return rows


def run() -> dict[str, Any]:
    pin = financial_v2_pin_decision(tickers_with_new_qualified_core=2, unresolved_schema_ambiguity=False)
    daily = {
        "session": "2026-09-29",
        "live_daily_run": False,
        "note": "Official citations JSONL already stored HPG 2022/2023 line-60 totals; FPT/GAS line-61-as-net_income lived in OCR/P2C2 panels. Overlay adds current-authority FPT/GAS totals and HPG/GAS attributable facts. Market/technical/liquidity/PIT/sizing loaders do not consume these income identities.",
        "unexplained_drift_count": 0,
        "financial_v2_pin": FINANCIAL_V2_PIN,
    }
    report = build_public_report(
        consumer_impact=_consumer_impact(),
        daily_impact=daily,
        financial_v2={"authority_version": pin["current_authority_version"], "changed": False,
                      "decision": pin["decision"], "tickers_with_new_qualified_core": 2},
        unexplained_drift_count=0,
    )
    return {
        "report": report,
        "corrections": build_all_correction_records(),
        "facts": current_authority_fact_rows(),
    }


def write_outputs(result: dict[str, Any], public_root: Path) -> None:
    public_root.mkdir(parents=True, exist_ok=True)
    (public_root / PUBLIC_REPORT).write_text(
        json.dumps(result["report"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    (public_root / PUBLIC_CORRECTIONS).write_text(render_jsonl(result["corrections"]), encoding="utf-8", newline="\n")
    (public_root / PUBLIC_FACTS).write_text(render_jsonl(result["facts"]), encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-root", type=Path, default=ROOT / PUBLIC_DIR)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    result = run()
    if args.write:
        write_outputs(result, args.public_root)
    print(json.dumps({"milestone_id": MILESTONE_ID, "contract_version": CONTRACT_VERSION,
                      "artifact_sha256": result["report"]["artifact_sha256"],
                      "fact_count": len(result["facts"]), "correction_count": len(result["corrections"])},
                     ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
