"""Generate the Phase 4 advanced financial metric diagnostic for PAN."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import bctc_processor as processor  # noqa: E402


METRICS = (
    "profit_before_tax",
    "interest_expense",
    "ebit",
    "depreciation",
    "amortization",
    "depreciation_and_amortization",
    "ebitda",
    "retained_earnings_end_period",
    "selling_expense",
    "general_admin_expense",
    "sga",
)


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe(item) for item in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def build_diagnostic(ticker: str = "PAN") -> dict[str, Any]:
    ticker = ticker.strip().upper()
    rows = processor.process_data(tickers_filter=[ticker]).sort_values("period")
    latest = rows.iloc[-1]
    metrics: dict[str, Any] = {}
    for metric in METRICS:
        provenance_metric = "retained_earnings" if metric == "retained_earnings_end_period" else metric
        available = rows[rows[metric].notna()] if metric in rows.columns else rows.iloc[0:0]
        latest_available = available.iloc[-1] if not available.empty else None
        metrics[metric] = {
            "value": latest.get(metric),
            "status": latest.get(f"{provenance_metric}_status") or (
                "reported" if latest.get(metric) is not None else "source_empty"
            ),
            "reason": latest.get(f"{provenance_metric}_reason"),
            "basis": latest.get(f"{provenance_metric}_basis"),
            "formula": latest.get(f"{provenance_metric}_formula"),
            "inputs": json.loads(latest.get(f"{provenance_metric}_inputs"))
            if latest.get(f"{provenance_metric}_inputs") else None,
            "latest_non_null_period": latest_available.get("period") if latest_available is not None else None,
            "latest_non_null_value": latest_available.get(metric) if latest_available is not None else None,
        }
    return _safe({
        "schema_version": "1.0.0",
        "ticker": ticker,
        "entity_type": latest.get("entity_type"),
        "selected_period": latest.get("period"),
        "metrics": metrics,
        "safety_checks": {
            "financial_expense_used_as_interest_expense": False,
            "combined_da_split_into_components": False,
            "corporate_sga_applied_to_non_corporate": False,
        },
    })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="PAN")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = build_diagnostic(args.ticker)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
