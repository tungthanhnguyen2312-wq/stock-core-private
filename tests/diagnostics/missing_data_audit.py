#!/usr/bin/env python3
"""Read-only Phase 0 audit for PAN missing context data.

The audit intentionally does not import or modify the production pipeline.  It
reads the raw BCTC CSV files, normalized financial snapshot, SQLite data, and
the exported ticker context to identify the layer at which each value is lost.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VNSTOCK_ROOT = Path(__file__).resolve().parents[2]
AI_ANALYZE_ROOT = VNSTOCK_ROOT.parent / "AI ANALYZE"
sys.path.insert(0, str(VNSTOCK_ROOT))

from financial_mapping import get_default_registry  # noqa: E402

FINANCIAL_SPECS = {
    "operating_cash_flow": {
        "item_ids": ["operating_cash_flow"],
        "report_types": ["cash_flow"],
    },
    "ebit": {
        "item_ids": ["ebit", "earnings_before_interest_and_taxes"],
        "report_types": ["income_statement"],
        "derivation_inputs": ["profit_before_tax", "interest_expense"],
    },
    "ebitda": {
        "item_ids": ["ebitda", "earnings_before_interest_taxes_depreciation_and_amortization"],
        "report_types": ["income_statement", "cash_flow"],
        "derivation_inputs": ["ebit", "depreciation", "amortization"],
    },
    "interest_expense": {
        "item_ids": ["of_which_interest_expense", "borrowing_costs"],
        "report_types": ["income_statement", "cash_flow"],
    },
    "retained_earnings": {
        "item_ids": [
            "undistributed_earnings",
            "beginning_accumulated_undistributed_earnings",
            "current_period_undistributed_earnings",
        ],
        "report_types": ["balance_sheet"],
    },
    "depreciation": {
        "item_ids": ["depreciation_of_fixed_assets_and_investment_properties"],
        "report_types": ["cash_flow"],
    },
    "sga": {
        "item_ids": ["selling_expenses", "admin_expenses"],
        "report_types": ["income_statement"],
        "derivation_inputs": ["selling_expenses", "admin_expenses"],
    },
}


def _number(value: Any) -> float | int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _normalize_period(raw: str) -> str:
    text = str(raw).strip().upper()
    match = re.match(r"^(\d{4})[-_.]?Q([1-4])(?:[._-]\d+)?$", text)
    if match:
        return f"{match.group(1)}-Q{match.group(2)}"
    match = re.match(r"^(\d{4})(?:[-_.]?(?:YEAR|NĂM))?(?:[._-]\d+)?$", text)
    return match.group(1) if match else text


def _period_key(period: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d{4})(?:-Q([1-4]))?", period or "")
    return (int(match.group(1)), int(match.group(2) or 5)) if match else (-1, -1)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _workspace_path(path: Path, workspace_root: Path) -> str:
    """Return a portable path without leaking the local user profile."""
    try:
        return path.resolve().relative_to(workspace_root.resolve()).as_posix()
    except ValueError:
        return path.name


def _raw_financial_rows(root: Path, ticker: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((root / "data_bctc").glob(f"{ticker}_*.csv")):
        for row in _read_csv(path):
            values = []
            for column, raw_value in row.items():
                if not re.match(r"^\d{4}", str(column)):
                    continue
                value = _number(raw_value)
                if value is not None:
                    values.append({"raw_period": column, "period": _normalize_period(column), "value": value})
            rows.append(
                {
                    "source_file": str(path),
                    "source": row.get("source") or None,
                    "report_type": row.get("report_type") or None,
                    "raw_label": row.get("item") or None,
                    "raw_label_en": row.get("item_en") or None,
                    "item_id": row.get("item_id") or None,
                    "values": values,
                }
            )
    return rows


def _mapping_target_exists(processor_path: Path, target: str) -> bool:
    if not processor_path.exists():
        return False
    text = processor_path.read_text(encoding="utf-8")
    mapping_end = text.find("# ==========================================\n# LOGGING SETUP")
    mapping_text = text[:mapping_end] if mapping_end >= 0 else text
    static_mapping = re.search(rf'["\']{re.escape(target)}["\']\s*:\s*\[', mapping_text) is not None
    registry = get_default_registry()
    registry_mapping = target in registry.reported_metrics()
    registry_derivation = registry.derivation_for(target, "corporate") is not None
    return static_mapping or registry_mapping or registry_derivation


def _latest_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    available = [
        {**candidate, "selected_raw_value": value}
        for candidate in candidates
        for value in candidate["values"]
    ]
    if not available:
        return None
    return max(available, key=lambda item: (_period_key(item["selected_raw_value"]["period"]), item["selected_raw_value"]["raw_period"]))


def _snapshot_state(root: Path, ticker: str) -> dict[str, Any]:
    rows = [row for row in _read_csv(root / "financial_snapshot.csv") if (row.get("ticker") or "").upper() == ticker]
    rows.sort(key=lambda row: _period_key(row.get("period", "")))
    return {"rows": rows, "latest": rows[-1] if rows else None}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _db_state(root: Path, ticker: str) -> dict[str, Any]:
    path = root / "vn_stock.db"
    if not path.exists():
        return {"exists": False, "shareholder_progress": None, "shareholder_count": 0, "news_count": 0, "news_columns": []}
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        progress = connection.execute("SELECT status, rows, updated FROM shareholders_progress WHERE ticker=?", (ticker,)).fetchone()
        shareholder_count = connection.execute("SELECT COUNT(*) FROM shareholders WHERE ticker=?", (ticker,)).fetchone()[0]
        news_count = connection.execute("SELECT COUNT(*) FROM news").fetchone()[0]
        news_columns = [row["name"] for row in connection.execute("PRAGMA table_info(news)")]
    finally:
        connection.close()
    return {
        "exists": True,
        "database": _workspace_path(path, root.parent),
        "shareholder_progress": dict(progress) if progress else None,
        "shareholder_count": shareholder_count,
        "news_count": news_count,
        "news_columns": news_columns,
    }


def _financial_metric(
    ticker: str,
    metric: str,
    spec: dict[str, Any],
    raw_rows: list[dict[str, Any]],
    snapshot: dict[str, Any],
    context_financial: dict[str, Any],
    processor_path: Path,
) -> dict[str, Any]:
    candidates = [
        row for row in raw_rows
        if row["item_id"] in spec["item_ids"] and row["report_type"] in spec["report_types"]
    ]
    selected = _latest_candidate(candidates)
    latest_snapshot = snapshot["latest"] or {}
    mapping_found = _mapping_target_exists(processor_path, metric)
    snapshot_has_field = bool(snapshot["rows"] and metric in snapshot["rows"][0])
    latest_snapshot_value = _number(latest_snapshot.get(metric)) if snapshot_has_field else None
    snapshot_status = latest_snapshot.get(f"{metric}_status") or None
    latest_non_null_snapshot = next(
        (
            {"period": row.get("period"), "value": _number(row.get(metric))}
            for row in reversed(snapshot["rows"])
            if _number(row.get(metric)) is not None
        ),
        None,
    ) if snapshot_has_field else None

    if metric == "operating_cash_flow" and candidates and mapping_found and latest_non_null_snapshot and latest_snapshot_value is None:
        reason = "latest_period_value_null_no_non_null_fallback"
    elif snapshot_has_field:
        reason = latest_snapshot.get(f"{metric}_reason") or None
    elif metric in {"ebit", "ebitda", "sga"} and mapping_found:
        reason = "derivation_declared_not_executed"
    elif candidates and mapping_found and not snapshot_has_field:
        reason = "registry_mapping_available_snapshot_not_rebuilt"
    elif metric in {"ebit", "ebitda", "sga"} and not mapping_found:
        reason = "derivation_not_implemented"
    elif candidates and not mapping_found:
        reason = "item_mapping_not_found"
    elif not candidates:
        reason = "raw_item_not_found"
    else:
        reason = None

    return {
        "ticker": ticker,
        "metric": metric,
        "raw_data_found": bool(candidates),
        "raw_candidates": candidates,
        "latest_raw_candidate": selected,
        "mapping_found": mapping_found,
        "mapping_rule": f"ITEM_MAPPING.{metric}" if mapping_found else None,
        "snapshot_field_present": snapshot_has_field,
        "selected_period": latest_snapshot.get("period") or context_financial.get("latest_period"),
        "selected_value_before_normalization": latest_snapshot_value,
        "selected_value_after_normalization": latest_snapshot_value,
        "latest_non_null_snapshot": latest_non_null_snapshot,
        "context_value": context_financial.get(metric),
        "context_meta": context_financial.get(f"{metric}_meta"),
        "snapshot_status": snapshot_status,
        "snapshot_formula": latest_snapshot.get(f"{metric}_formula") or None,
        "snapshot_source": latest_snapshot.get(f"{metric}_source") or None,
        "snapshot_period": latest_snapshot.get(f"{metric}_period") or None,
        "basis": "reported" if metric == "operating_cash_flow" else None,
        "raw_unit": None,
        "normalized_unit": None,
        "unit_status": "unit_metadata_missing",
        "derivation_inputs": spec.get("derivation_inputs", []),
        "reason": reason,
    }


def build_audit(
    ticker: str = "PAN",
    vnstock_root: Path = VNSTOCK_ROOT,
    ai_analyze_root: Path = AI_ANALYZE_ROOT,
) -> dict[str, Any]:
    ticker = ticker.strip().upper()
    raw_rows = _raw_financial_rows(vnstock_root, ticker)
    for row in raw_rows:
        row["source_file"] = _workspace_path(Path(row["source_file"]), vnstock_root.parent)
    snapshot = _snapshot_state(vnstock_root, ticker)
    context_path = ai_analyze_root / "exports" / "context_packages" / f"{ticker}_context.json"
    context = _load_json(context_path)
    context_financial = context.get("financial_summary", {})
    database = _db_state(vnstock_root, ticker)
    processor_path = vnstock_root / "bctc_processor.py"

    metrics = {
        name: _financial_metric(ticker, name, spec, raw_rows, snapshot, context_financial, processor_path)
        for name, spec in FINANCIAL_SPECS.items()
    }
    raw_item_ids = {row["item_id"] for row in raw_rows if row["values"]}
    input_evidence = {
        "profit_before_tax": "profit_before_tax" in raw_item_ids,
        "interest_expense": bool({"of_which_interest_expense", "borrowing_costs"} & raw_item_ids),
        "depreciation": "depreciation_of_fixed_assets_and_investment_properties" in raw_item_ids,
        "amortization": bool({"amortization", "amortization_expense"} & raw_item_ids),
        "selling_expenses": "selling_expenses" in raw_item_ids,
        "admin_expenses": "admin_expenses" in raw_item_ids,
    }
    metrics["ebit"]["derivation_input_evidence"] = {
        key: input_evidence[key] for key in ("profit_before_tax", "interest_expense")
    }
    metrics["ebitda"]["derivation_input_evidence"] = {
        "ebit": "derivable_but_not_materialized" if all(metrics["ebit"]["derivation_input_evidence"].values()) else False,
        "depreciation": input_evidence["depreciation"],
        "amortization": input_evidence["amortization"],
    }
    metrics["sga"]["derivation_input_evidence"] = {
        key: input_evidence[key] for key in ("selling_expenses", "admin_expenses")
    }
    news_columns = set(database["news_columns"])
    news_mapping_diagnostic_path = vnstock_root / "reports" / "news_mapping_diagnostics_pan.json"
    news_mapping_diagnostic = _load_json(news_mapping_diagnostic_path) if news_mapping_diagnostic_path.exists() else {}
    canonical_mapping_available = (
        (vnstock_root / "news_ticker_mapping.py").exists()
        and (vnstock_root / "config" / "ticker_aliases.csv").exists()
    )
    metrics["news_summary"] = {
        "ticker": ticker,
        "metric": "news_summary",
        "raw_data_found": database["news_count"] > 0,
        "raw_row_count": database["news_count"],
        "raw_schema": database["news_columns"],
        "mapping_found": "ticker" in news_columns or canonical_mapping_available,
        "mapping_method": "source_ticker_field" if "ticker" in news_columns else (
            "canonical_alias_registry" if canonical_mapping_available else None
        ),
        "mapping_version": news_mapping_diagnostic.get("mapping_version"),
        "company_news_count": news_mapping_diagnostic.get("company_news_count"),
        "sector_news_count": news_mapping_diagnostic.get("sector_news_count"),
        "market_news_count": news_mapping_diagnostic.get("market_news_count"),
        "selected_period": None,
        "context_value": context.get("news_summary"),
        "reason": news_mapping_diagnostic.get("status") if canonical_mapping_available else (
            "canonical_ticker_field_missing" if "ticker" not in news_columns else None
        ),
    }
    progress = database["shareholder_progress"]
    if progress is None and database["shareholder_count"] == 0:
        shareholder_reason = "ticker_not_queried"
    elif progress and progress.get("status") == "empty":
        shareholder_reason = "sources_returned_empty"
    elif database["shareholder_count"] == 0:
        shareholder_reason = "no_usable_shareholder_rows"
    else:
        shareholder_reason = None
    metrics["shareholder_summary"] = {
        "ticker": ticker,
        "metric": "shareholder_summary",
        "raw_data_found": database["shareholder_count"] > 0,
        "raw_row_count": database["shareholder_count"],
        "progress": progress,
        "sources_configured": ["VCI", "KBS"],
        "sources_attempted": [] if progress is None else ["not_recorded_by_current_progress_schema"],
        "context_value": context.get("shareholder_summary"),
        "reason": shareholder_reason,
    }

    return {
        "schema_version": "0.1.0",
        "phase": 0,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ticker": ticker,
        "audit_mode": "read_only",
        "sources": {
            "raw_financial_files": sorted({row["source_file"] for row in raw_rows}),
            "financial_snapshot": _workspace_path(vnstock_root / "financial_snapshot.csv", vnstock_root.parent),
            "database": database.get("database"),
            "ticker_context": _workspace_path(context_path, vnstock_root.parent),
        },
        "cross_cutting_findings": {
            "unit_metadata": "missing_from_raw_bctc_schema",
            "period_basis": "unconfirmed_for_kbs_columns_with_numeric_suffix",
            "period_normalization_risk": "2025-Q4 and 2025-Q4_1 normalize to the same key; processor groupby(first) can hide basis/restatement differences",
        },
        "metrics": metrics,
        "files_and_functions_for_later_phases": [
            {"file": _workspace_path(vnstock_root / "bctc_processor.py", vnstock_root.parent), "functions": ["load_and_melt_file", "process_data"], "phases": [2, 3, 4]},
            {"file": _workspace_path(ai_analyze_root / "builders" / "build_ticker_context.py", vnstock_root.parent), "functions": ["load_financial_slice", "load_news_slice", "load_shareholder_slice"], "phases": [1, 3, 5, 6, 7]},
            {"file": _workspace_path(vnstock_root / "news_sync.py", vnstock_root.parent), "functions": ["init_db", "sync_feed"], "phases": [5]},
            {"file": _workspace_path(vnstock_root / "shareholders_sync.py", vnstock_root.parent), "functions": ["fetch_shareholders", "set_progress", "run_sync"], "phases": [6]},
        ],
    }


def build_summary_markdown(audit: dict[str, Any]) -> str:
    metrics = audit["metrics"]
    lines = [
        "# VNSTOCK Missing Data Audit — PAN",
        "",
        f"Generated: `{audit['generated_at']}`",
        "Mode: read-only; no production business logic changed.",
        "",
        "## Kết luận",
        "",
        "| Metric | Raw | Mapping | Kỳ context | Nguyên nhân |",
        "|---|---:|---:|---|---|",
    ]
    for name, item in metrics.items():
        lines.append(
            f"| `{name}` | {'yes' if item.get('raw_data_found') else 'no'} | "
            f"{'yes' if item.get('mapping_found') else 'no'} | "
            f"{item.get('selected_period') or 'n/a'} | `{item.get('reason') or 'none'}` |"
        )
    ocf = metrics["operating_cash_flow"]
    lines.extend(
        [
            "",
            "## Phát hiện chính",
            "",
            f"- OCF có raw row và mapping hợp lệ. Snapshot gần nhất có số là `{ocf.get('latest_non_null_snapshot')}`; "
            f"context chọn `{ocf.get('selected_period')}` có giá trị null và không fallback về kỳ có số.",
            "- Interest expense, retained earnings và depreciation đều có raw item nhưng chưa có mapping output.",
            "- EBIT, EBITDA và SG&A chưa có derivation trong processor; không được phép tự điền 0 cho input thiếu.",
            f"- EBITDA chưa đủ bằng chứng đầu vào an toàn: `{metrics['ebitda'].get('derivation_input_evidence')}`; "
            "đặc biệt không được coi amortization thiếu là 0.",
            "- News có dữ liệu nguồn nhưng schema không có ticker canonical, nên builder chủ động không suy diễn ticker.",
            f"- Shareholders của PAN: `{metrics['shareholder_summary']['reason']}`; không được diễn giải thành không có cổ đông lớn.",
            "- Raw BCTC hiện không mang metadata đơn vị, nên unit normalization chưa thể được xác nhận.",
            "- `2025-Q4` và `2025-Q4_1` cùng bị normalize thành `2025-Q4`; basis/restatement của hậu tố `_1` chưa được xác nhận.",
            "",
            "## File/function cần xử lý ở phase sau",
            "",
        ]
    )
    for item in audit["files_and_functions_for_later_phases"]:
        lines.append(f"- `{item['file']}` — {', '.join(item['functions'])} (phase {', '.join(map(str, item['phases']))})")
    lines.append("")
    return "\n".join(lines)


def write_reports(audit: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "missing_data_audit_pan.json"
    md_path = output_dir / "missing_data_audit_summary.md"
    with json_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(audit, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    md_path.write_text(build_summary_markdown(audit), encoding="utf-8", newline="\n")
    return json_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit missing PAN context data without changing the pipeline")
    parser.add_argument("--ticker", default="PAN")
    parser.add_argument("--output-dir", type=Path, default=VNSTOCK_ROOT / "reports")
    args = parser.parse_args()
    audit = build_audit(args.ticker)
    paths = write_reports(audit, args.output_dir)
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
