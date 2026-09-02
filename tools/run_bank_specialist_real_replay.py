#!/usr/bin/env python3
"""Offline TCBS capture import and bank specialist replay; never calls TCBS."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import financial_analysis_engine_v2 as engine  # noqa: E402
import tcbs_bank_capture_import as importer  # noqa: E402

DEFAULT_CAPTURE = Path(r"C:\Projects\StockLookup\operations-review\tcbs-bank-public-company-capture-20260901\tcbs_bank_public_company_capture_v1.json")
TARGET_TICKERS = ("ABB", "ACB", "BID", "MBB", "TCB", "VCB")

def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()).hexdigest()

def _synthetic_bundle() -> dict:
    captures = []
    for ticker in TARGET_TICKERS:
        raw = {"result": [{"ticker": ticker, "year": 2025, "quarter": 2, "customerLoan": 1000, "deposit": 1200, "nonPerformingLoan": 40, "provision": 60}, {"ticker": ticker, "year": 2026, "quarter": 2, "customerLoan": 1100, "deposit": 1300, "nonPerformingLoan": 44, "provision": 66}]}
        captures.append({"provider": "TCBS", "tool_name": "getBalanceSheetForBank", "ticker": ticker, "captured_at": "2026-09-02T00:00:00+07:00", "raw_response": raw, "raw_response_sha256": _hash(raw)})
        raw = {"result": [{"ticker": ticker, "year": 2026, "quarter": 2, "operationExpense": -300, "totalOperationIncome": 600}]}
        captures.append({"provider": "TCBS", "tool_name": "getIncomeStatementForBank", "ticker": ticker, "captured_at": "2026-09-02T00:00:00+07:00", "raw_response": raw, "raw_response_sha256": _hash(raw)})
        raw = {"result": [{"ticker": ticker, "year": 2026, "quarter": 2, "netInterestMargin": 0.03}]}
        captures.append({"provider": "TCBS", "tool_name": "getFinancialRatioForBank", "ticker": ticker, "captured_at": "2026-09-02T00:00:00+07:00", "raw_response": raw, "raw_response_sha256": _hash(raw)})
    bundle = {"capture_contract": importer.SOURCE_CAPTURE_CONTRACT, "tickers": list(TARGET_TICKERS), "captures": captures}
    bundle["bundle_sha256"] = _hash(bundle)
    return bundle

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--import-output", type=Path)
    args = parser.parse_args(argv)
    capture_path = args.capture or DEFAULT_CAPTURE
    real = capture_path.is_file()  # one start-of-job existence check; no poll/retry
    bundle = importer.import_capture_file(capture_path) if real else importer.import_capture_bundle(_synthetic_bundle())
    artifact = engine.build_artifact(tickers=TARGET_TICKERS, rows=[], issuer_types={ticker: "bank" for ticker in TARGET_TICKERS}, source_identities={"tcbs_capture_bundle": bundle["content_identity"]}, requested_at="2026-09-02T00:00:00+07:00", bank_components=bundle["observations"])
    report = {"milestone": "TCBS_BANK_CAPTURE_IMPORT_AND_REAL_REPLAY_V1", "real_capture_status": "PRESENT_AND_REPLAYED" if real else "NOT_PRESENT_AT_JOB_START", "capture_contract": bundle["source_capture_contract"], "captures_seen": bundle["captures_seen"], "captures_imported": bundle["captures_imported"], "captures_failed": bundle["captures_failed"], "bank_tickers": list(TARGET_TICKERS), "observation_counts_by_metric": dict(sorted(Counter(x["metric_id"] for x in bundle["observations"]).items())), "privacy_rejections": len(bundle["privacy_rejections"]), "conflict_count": len(bundle["conflicts"]), "feature_fitness": {f: dict(sorted(Counter(artifact["records"][t]["features"][f]["fitness"] for t in TARGET_TICKERS).items())) for f in engine.BANK_FEATURE_IDS}, "bank_states": {t: artifact["records"][t]["states"] for t in TARGET_TICKERS}, "financial_v2_ticker_denominator": artifact["coverage"]["ticker_denominator"], "tcbs_live_calls": 0, "oauth_implemented": False, "daily_pipeline_changed": False, "authority_changed": False}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.import_output:
        args.import_output.parent.mkdir(parents=True, exist_ok=True)
        args.import_output.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
