"""Generate the Phase 3 Operating Cash Flow diagnostic for one ticker."""

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


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def build_diagnostic(ticker: str = "PAN") -> dict[str, Any]:
    ticker = ticker.strip().upper()
    raw_path = ROOT / "data_bctc" / f"{ticker}_cash_flow_quarter.csv"
    raw = processor.diagnose_ocf_raw(raw_path)
    snapshot = processor.process_data(tickers_filter=[ticker])
    rows = snapshot[snapshot["ticker"] == ticker].sort_values("period")
    ocf_columns = [
        "period",
        "operating_cash_flow_reported",
        "operating_cash_flow_ytd",
        "operating_cash_flow_quarter",
        "operating_cash_flow_quarter_status",
        "operating_cash_flow_ttm",
        "operating_cash_flow_ttm_status",
        "operating_cash_flow_ttm_reason",
        "operating_cash_flow",
        "operating_cash_flow_basis",
        "operating_cash_flow_basis_confidence",
        "operating_cash_flow_raw_unit",
        "operating_cash_flow_normalized_unit",
        "operating_cash_flow_unit_multiplier",
        "operating_cash_flow_unit_status",
    ]
    period_outputs = rows[ocf_columns].to_dict("records")
    latest_financial_period = rows.iloc[-1]["period"] if not rows.empty else None
    selected = processor.select_latest_non_null_reported_value(
        period_outputs, "operating_cash_flow"
    )
    return _json_safe({
        "schema_version": "1.0.0",
        "ticker": ticker,
        "raw_detection": raw,
        "period_outputs": period_outputs,
        "selection": {
            "latest_financial_period": latest_financial_period,
            "latest_non_null_reported_period": selected.get("period") if selected else None,
            "value": selected.get("operating_cash_flow") if selected else None,
            "basis": selected.get("operating_cash_flow_basis") if selected else None,
            "latest_null_period_skipped": bool(
                selected and selected.get("period") != latest_financial_period
            ),
            "ttm_status": selected.get("operating_cash_flow_ttm_status") if selected else "source_empty",
            "quarter_status": selected.get("operating_cash_flow_quarter_status") if selected else "source_empty",
        },
        "policy": {
            "ttm_never_overwrites_reported_when_null": True,
            "ytd_is_not_labeled_as_standalone_without_comparable_prior_ytd": True,
            "unknown_raw_unit_is_not_guessed": True,
        },
    })


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="PAN")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    diagnostic = build_diagnostic(args.ticker)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(diagnostic, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
