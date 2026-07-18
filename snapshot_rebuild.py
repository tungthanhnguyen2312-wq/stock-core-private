#!/usr/bin/env python3
"""Build, validate, compare and atomically replace the financial snapshot."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

import bctc_processor as processor
from financial_mapping import get_default_registry


ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "financial_snapshot.csv"
PARQUET_PATH = ROOT / "financial_snapshot.parquet"
NEXT_CSV = ROOT / "financial_snapshot.next.csv"
NEXT_PARQUET = ROOT / "financial_snapshot.next.parquet"
REPORT_JSON = ROOT / "reports" / "financial_snapshot_rebuild.json"
REPORT_MD = ROOT / "reports" / "financial_snapshot_rebuild.md"
SCHEMA_VERSION = "2.0"

ADVANCED_FIELDS = [
    "ebit", "ebit_status", "ebit_formula", "ebit_source", "ebit_period",
    "ebitda", "ebitda_status", "ebitda_formula", "ebitda_source", "ebitda_period",
    "interest_expense", "interest_expense_status", "retained_earnings",
    "retained_earnings_status", "depreciation", "amortization",
    "depreciation_and_amortization", "selling_expense", "general_admin_expense",
    "sga", "sga_status",
]
PAN_EXPECTED = {
    "ebit": 600_682_628_000.0,
    "ebit_status": "derived",
    "ebit_formula": "profit_before_tax + interest_expense",
    "sga": 353_782_849_000.0,
    "sga_status": "derived",
    "sga_formula": "selling_expense + general_admin_expense",
    "retained_earnings": 2_618_950_443_317.0,
    "retained_earnings_status": "reported",
    "ebitda_status": "insufficient_periods",
}
REPRESENTATIVE_TICKERS = ["PAN", "HPG", "VCB", "SSI", "BVH", "EVF"]


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.parent.resolve()).as_posix()
    except ValueError:
        return path.name


def _period_key(value: Any) -> tuple[int, int]:
    text = str(value or "")
    try:
        if "-Q" in text:
            year, quarter = text.split("-Q", 1)
            return int(year), int(quarter)
        return int(text), 5
    except ValueError:
        return -1, -1


def _json_value(value: Any) -> Any:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if hasattr(value, "item"):
        value = value.item()
    return value


def snapshot_stats(frame: pd.DataFrame) -> dict[str, Any]:
    tickers = sorted(frame["ticker"].dropna().astype(str).unique()) if "ticker" in frame else []
    periods = sorted(frame["period"].dropna().astype(str).unique(), key=_period_key) if "period" in frame else []
    return {
        "row_count": int(len(frame)),
        "column_count": int(len(frame.columns)),
        "ticker_count": len(tickers),
        "period_count": len(periods),
        "period_min": periods[0] if periods else None,
        "period_max": periods[-1] if periods else None,
        "duplicate_key_count": int(frame.duplicated(["ticker", "period"]).sum())
        if {"ticker", "period"}.issubset(frame.columns) else None,
        "tickers": tickers,
        "periods": periods,
    }


def report_stats(frame: pd.DataFrame) -> dict[str, Any]:
    """Compact public report stats; full sets are used only during validation."""
    return {key: value for key, value in snapshot_stats(frame).items() if key not in {"tickers", "periods"}}


def _metric_null_rates(frame: pd.DataFrame) -> dict[str, float | None]:
    metrics = [
        "operating_cash_flow", "ebit", "ebitda", "interest_expense",
        "retained_earnings", "depreciation", "amortization",
        "depreciation_and_amortization", "selling_expense",
        "general_admin_expense", "sga",
    ]
    return {
        metric: round(float(frame[metric].isna().mean()), 6) if metric in frame else None
        for metric in metrics
    }


def _metric_coverage(frame: pd.DataFrame) -> dict[str, dict[str, int]]:
    output: dict[str, dict[str, int]] = {}
    for metric in ["operating_cash_flow", "ebit", "ebitda", "interest_expense", "retained_earnings", "depreciation", "sga"]:
        if metric not in frame:
            continue
        status_field = f"{metric}_status"
        output[metric] = {
            "non_null_values": int(frame[metric].notna().sum()),
            "reported": int((frame.get(status_field) == "reported").sum()) if status_field in frame else 0,
            "derived": int((frame.get(status_field) == "derived").sum()) if status_field in frame else 0,
            "not_applicable": int((frame.get(status_field) == "not_applicable").sum()) if status_field in frame else 0,
        }
    return output


def _pan_validation(frame: pd.DataFrame) -> dict[str, Any]:
    rows = frame[(frame["ticker"] == "PAN") & (frame["period"] == "2026-Q1")]
    if len(rows) != 1:
        return {"passed": False, "reason": f"expected_one_pan_2026_q1_row;found={len(rows)}"}
    row = rows.iloc[0]
    actual = {field: _json_value(row.get(field)) for field in PAN_EXPECTED}
    mismatches: dict[str, dict[str, Any]] = {}
    for field, expected in PAN_EXPECTED.items():
        observed = actual[field]
        equal = (
            math.isclose(float(observed), expected, rel_tol=0.0, abs_tol=0.5)
            if isinstance(expected, float) and observed is not None
            else observed == expected
        )
        if not equal:
            mismatches[field] = {"expected": expected, "actual": observed}
    provenance = {
        metric: {
            key: _json_value(row.get(f"{metric}_{key}"))
            for key in ("status", "basis", "reason", "formula", "inputs", "source", "period")
        }
        for metric in ("ebit", "ebitda", "retained_earnings", "sga")
    }
    return {"passed": not mismatches, "actual": actual, "mismatches": mismatches, "provenance": provenance}


def _representative_validation(frame: pd.DataFrame) -> dict[str, Any]:
    registry = get_default_registry()
    results: dict[str, Any] = {}
    for ticker in REPRESENTATIVE_TICKERS:
        rows = frame[frame["ticker"] == ticker].copy()
        entity_type = registry.entity_type_for(ticker)
        if rows.empty:
            results[ticker] = {"passed": False, "entity_type": entity_type, "reason": "ticker_missing"}
            continue
        rows["_period_key"] = rows["period"].map(_period_key)
        latest = rows.sort_values("_period_key").iloc[-1]
        non_corporate_sga_ok = True
        if entity_type != "corporate":
            non_corporate_sga_ok = bool(rows["sga"].isna().all() and (rows["sga_status"] == "not_applicable").all())
        # item E: confirmed-non-corporate tickers (bank/securities/insurance/finance_company —
        # NOT the broader "unknown" default) must never surface ebit/ebitda as
        # insufficient_periods; a structurally-inapplicable concept is not_applicable, not a
        # data gap. See bctc_processor.CONFIRMED_NON_CORPORATE for why this is a whitelist.
        non_corporate_ebit_ebitda_ok = True
        if entity_type in processor.CONFIRMED_NON_CORPORATE:
            non_corporate_ebit_ebitda_ok = bool(
                rows["ebit_status"].isin(["reported", "derived", "not_applicable"]).all()
                and rows["ebitda_status"].isin(["reported", "derived", "not_applicable"]).all()
            )
        advanced_statuses = {
            metric: _json_value(latest.get(f"{metric}_status"))
            for metric in ("ebit", "ebitda", "interest_expense", "retained_earnings", "sga")
        }
        ocf_statuses = sorted(set(rows["operating_cash_flow_status"].dropna().astype(str)))
        passed = (
            non_corporate_sga_ok
            and non_corporate_ebit_ebitda_ok
            and all(value is not None for value in advanced_statuses.values())
        )
        results[ticker] = {
            "passed": passed,
            "entity_type": entity_type,
            "latest_period": _json_value(latest.get("period")),
            "advanced_statuses": advanced_statuses,
            "ocf_statuses": ocf_statuses,
            "non_corporate_sga_ok": non_corporate_sga_ok,
            "non_corporate_ebit_ebitda_ok": non_corporate_ebit_ebitda_ok,
        }
    return results


def validate_snapshot(new: pd.DataFrame, old: pd.DataFrame, parquet: pd.DataFrame) -> dict[str, Any]:
    old_stats = snapshot_stats(old)
    new_stats = snapshot_stats(new)
    missing_columns = sorted({"schema_version", "ticker", "period", "period_type", *ADVANCED_FIELDS} - set(new.columns))
    schema_versions = sorted(set(new.get("schema_version", pd.Series(dtype=str)).dropna().astype(str)))
    missing_tickers = sorted(set(old_stats["tickers"]) - set(new_stats["tickers"]))
    missing_periods = sorted(set(old_stats["periods"]) - set(new_stats["periods"]), key=_period_key)
    status_fields = [field for field in new.columns if field.endswith("_status") and field.startswith(tuple(
        ["ebit", "ebitda", "interest_expense", "retained_earnings", "depreciation", "amortization", "sga"]
    ))]
    null_status_counts = {field: int(new[field].isna().sum()) for field in status_fields}
    normalized_units = sorted(set(new.get("operating_cash_flow_normalized_unit", pd.Series(dtype=str)).dropna().astype(str)))
    unknown_unit_rows = new.get(
        "operating_cash_flow_normalized_unit", pd.Series(index=new.index, dtype=str)
    ).eq("unknown")
    unknown_unit_statuses = sorted(set(
        new.loc[unknown_unit_rows, "operating_cash_flow_unit_status"].dropna().astype(str)
    )) if "operating_cash_flow_unit_status" in new else []
    known_units = set(normalized_units) - {"unknown"}
    explicit_unknown_units = not unknown_unit_rows.any() or unknown_unit_statuses == ["unit_unknown"]
    # item C: statement-level unit contract — every row must declare a currency/unit_status/
    # unit_evidence (even when the honest answer is "unconfirmed"), and any currency that IS
    # declared must be VND (the only currency this pipeline has ever supported).
    statement_currencies = sorted(set(new.get("statement_currency", pd.Series(dtype=str)).dropna().astype(str)))
    statement_unit_statuses = sorted(set(new.get("unit_status", pd.Series(dtype=str)).dropna().astype(str)))
    statement_currency_declared = (
        {"statement_currency", "statement_scale", "unit_status", "unit_evidence"}.issubset(new.columns)
        and set(statement_currencies).issubset({"VND"})
        and bool(new["statement_currency"].notna().all())
        and bool(new["unit_status"].notna().all())
        and bool(new["unit_evidence"].notna().all())
    )
    pan = _pan_validation(new)
    representatives = _representative_validation(new)
    financial_expense_mapping = get_default_registry().map_financial_item(
        "KBS", "corporate", "income_statement", "financial_expense", "Financial expense"
    )
    csv_parquet_semantic = new.shape == parquet.shape and list(new.columns) == list(parquet.columns)
    if csv_parquet_semantic:
        for column in new.columns:
            left, right = new[column], parquet[column]
            is_bool_column = pd.api.types.is_bool_dtype(left) or pd.api.types.is_bool_dtype(right)
            if not is_bool_column and pd.api.types.is_numeric_dtype(left) and pd.api.types.is_numeric_dtype(right):
                equal = bool(
                    pd.Series(
                        (left.isna() & right.isna())
                        | ((left - right).abs() <= (0.5 + right.abs() * 1e-12))
                    ).all()
                )
            else:
                # CSV and Parquet legitimately represent missing strings as
                # NaN and None, and schema_version as float/string.
                equal = left.astype("string").fillna("<NULL>").equals(
                    right.astype("string").fillna("<NULL>")
                )
            if not equal:
                csv_parquet_semantic = False
                break
    checks = {
        "required_columns": not missing_columns,
        "schema_version": schema_versions == [SCHEMA_VERSION],
        "row_count_not_reduced": new_stats["row_count"] >= old_stats["row_count"],
        "ticker_coverage_not_reduced": not missing_tickers,
        "period_coverage_not_reduced": not missing_periods,
        "duplicate_keys": new_stats["duplicate_key_count"] == 0,
        "advanced_status_complete": all(count == 0 for count in null_status_counts.values()),
        "unit_consistency": known_units.issubset({"VND"}) and explicit_unknown_units,
        "statement_currency_declared": statement_currency_declared,
        "csv_parquet_shape": new.shape == parquet.shape and list(new.columns) == list(parquet.columns),
        "csv_parquet_semantic": csv_parquet_semantic,
        "pan_values": bool(pan["passed"]),
        "representative_tickers": all(item["passed"] for item in representatives.values()),
        "financial_expense_not_interest": financial_expense_mapping is None,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "missing_columns": missing_columns,
        "missing_tickers": missing_tickers,
        "missing_periods": missing_periods,
        "schema_versions": schema_versions,
        "advanced_status_null_counts": null_status_counts,
        "normalized_units": normalized_units,
        "unknown_unit_statuses": unknown_unit_statuses,
        "statement_currencies": statement_currencies,
        "statement_unit_statuses": statement_unit_statuses,
        "pan_validation": pan,
        "representative_ticker_validation": representatives,
        "null_rates": _metric_null_rates(new),
        "metric_coverage": _metric_coverage(new),
    }


def render_markdown(report: dict[str, Any]) -> str:
    old, new = report["old_snapshot"], report["new_snapshot"]
    lines = [
        "# Financial snapshot rebuild", "",
        f"- Build timestamp: `{report['build_timestamp']}`",
        f"- Validation passed: `{str(report['validation']['passed']).lower()}`",
        f"- Replacement status: `{report['replacement_status']}`",
        f"- Rollback CSV: `{report['rollback']['csv']}`",
        f"- Rollback Parquet: `{report['rollback']['parquet']}`", "",
        "## Comparison", "",
        "| Measure | Old | New |", "|---|---:|---:|",
        f"| Rows | {old['row_count']} | {new['row_count']} |",
        f"| Tickers | {old['ticker_count']} | {new['ticker_count']} |",
        f"| Periods | {old['period_count']} | {new['period_count']} |",
        f"| Columns | {old['column_count']} | {new['column_count']} |",
        f"| Duplicate keys | {old['duplicate_key_count']} | {new['duplicate_key_count']} |", "",
        "## Validation checks", "",
    ]
    lines.extend(f"- `{name}`: `{str(passed).lower()}`" for name, passed in report["validation"]["checks"].items())
    lines.extend(["", "## PAN 2026-Q1", ""])
    for name, value in report["validation"]["pan_validation"].get("actual", {}).items():
        lines.append(f"- `{name}`: `{value}`")
    lines.extend(["", "## Representative tickers", ""])
    for ticker, item in report["validation"]["representative_ticker_validation"].items():
        lines.append(f"- `{ticker}` ({item['entity_type']}): `{'pass' if item['passed'] else 'fail'}`")
    lines.extend([
        "", "## Source quarantine", "",
        f"- Schema errors quarantined: `{report['input_sources']['quarantined_schema_error_count']}`",
    ])
    for item in report["input_sources"].get("quarantined_schema_errors", []):
        lines.append(f"- `{item['ticker']}` / `{item['report_type']}`: `{item['reason']}`; missing `{', '.join(item['missing_fields'])}`")
    lines.extend([
        "", "## Unit checks", "",
        f"- Normalized unit labels: `{', '.join(report['validation']['normalized_units']) or 'none'}`",
        f"- Unknown-unit statuses: `{', '.join(report['validation']['unknown_unit_statuses']) or 'none'}`",
        "- `unknown` remains explicit and is never promoted to VND without source metadata.",
        f"- Statement currencies declared: `{', '.join(report['validation']['statement_currencies']) or 'none'}`",
        f"- Statement unit statuses: `{', '.join(report['validation']['statement_unit_statuses']) or 'none'}`",
        "", "## Rollback", "",
        "Stop consumers, then copy both backup files above over the current CSV and Parquet as one maintenance operation.", "",
    ])
    return "\n".join(lines)


def write_report(report: dict[str, Any]) -> None:
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    REPORT_MD.write_text(render_markdown(report), encoding="utf-8")


def rebuild(replace: bool, reuse_next: bool = False) -> tuple[int, dict[str, Any]]:
    build_timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    old = pd.read_csv(CSV_PATH)
    source_diagnostics: list[dict[str, object]] = []
    if reuse_next:
        if not NEXT_CSV.exists() or not NEXT_PARQUET.exists():
            raise FileNotFoundError("--reuse-next requires both validated-build candidate files")
        if REPORT_JSON.exists():
            previous = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
            source_diagnostics = list(previous.get("input_sources", {}).get("quarantined_schema_errors", []))
    else:
        new = processor.process_data(
            schema_error_policy="quarantine", source_diagnostics=source_diagnostics
        )
        if new.empty:
            raise RuntimeError("Pipeline returned an empty snapshot")
        new.to_csv(NEXT_CSV, index=False, encoding="utf-8-sig")
        new.to_parquet(NEXT_PARQUET, index=False)
    csv_check = pd.read_csv(NEXT_CSV)
    parquet_check = pd.read_parquet(NEXT_PARQUET)
    validation = validate_snapshot(csv_check, old, parquet_check)
    suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    csv_backup = ROOT / f"financial_snapshot.csv.phase9.{suffix}.bak"
    parquet_backup = ROOT / f"financial_snapshot.parquet.phase9.{suffix}.bak"
    replacement_status = "not_requested"
    if replace and validation["passed"]:
        shutil.copy2(CSV_PATH, csv_backup)
        shutil.copy2(PARQUET_PATH, parquet_backup)
        try:
            os.replace(NEXT_CSV, CSV_PATH)
            os.replace(NEXT_PARQUET, PARQUET_PATH)
        except Exception:
            shutil.copy2(csv_backup, CSV_PATH)
            shutil.copy2(parquet_backup, PARQUET_PATH)
            raise
        replacement_status = "replaced"
    elif replace:
        replacement_status = "validation_failed_not_replaced"
    report = {
        "report_version": "1.0.0",
        "snapshot_schema_version": SCHEMA_VERSION,
        "build_timestamp": build_timestamp,
        "input_sources": {
            "root": _display_path(processor.INPUT_DIR),
            "csv_files": len(list(processor.INPUT_DIR.glob("*.csv"))),
            "parquet_files": len(list(processor.INPUT_DIR.glob("*.parquet"))),
            "pipeline": _display_path(Path(processor.__file__)),
            "quarantined_schema_errors": [
                {**item, "source": _display_path(Path(str(item["source"])))}
                for item in source_diagnostics
            ],
            "quarantined_schema_error_count": len(source_diagnostics),
        },
        "build_command": "python snapshot_rebuild.py --replace",
        "reused_existing_candidate": reuse_next,
        "old_snapshot": report_stats(old),
        "new_snapshot": report_stats(csv_check),
        "validation": validation,
        "replacement_status": replacement_status,
        "rollback": {"csv": _display_path(csv_backup), "parquet": _display_path(parquet_backup)},
        "generated_outputs": {"csv": _display_path(CSV_PATH), "parquet": _display_path(PARQUET_PATH)},
    }
    write_report(report)
    return (0 if validation["passed"] else 2), report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replace", action="store_true", help="Replace current snapshots only after validation passes")
    parser.add_argument("--reuse-next", action="store_true", help="Revalidate existing .next CSV/Parquet without rebuilding raw sources")
    args = parser.parse_args()
    code, report = rebuild(args.replace, reuse_next=args.reuse_next)
    print(json.dumps({
        "passed": report["validation"]["passed"],
        "replacement_status": report["replacement_status"],
        "report": str(REPORT_JSON),
    }, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
