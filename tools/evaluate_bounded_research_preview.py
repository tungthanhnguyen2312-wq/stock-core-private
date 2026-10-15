"""Explicit read-only retained evaluation. Writes only a new, external local result directory."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import personal_investment_decision_action_center as ac
from stocklookup_core.decision import bounded_research_preview as bounded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--current-operation", type=Path, required=True)
    parser.add_argument("--previous-operation", type=Path)
    parser.add_argument("--tickers", nargs="+", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    protected = [args.evidence_root, Path(__file__).resolve().parents[1]]
    if os.environ.get("STOCK_LOOKUP_RUNTIME_ROOT"):
        protected.append(Path(os.environ["STOCK_LOOKUP_RUNTIME_ROOT"]))
    if output.exists() or any(output.is_relative_to(root.resolve()) for root in protected):
        parser.error("output must be a NEW directory outside source and retained evidence roots")
    import psutil
    process = psutil.Process()
    before = process.memory_info()._asdict()
    io_before = process.io_counters()._asdict()
    started = time.monotonic()
    try:
        gate = bounded.resource_gate()
        preview = ac.evaluate_selected_research_preview(
            repo_root=args.evidence_root, session=args.session, tickers=args.tickers,
            current_operation=args.current_operation, previous_operation=args.previous_operation)
        rendered = ac.selected_research_preview_markdown(preview)
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "REAL_SESSION_REPLAY_BLOCKED", "reason": str(exc),
                          "elapsed_seconds": time.monotonic() - started}))
        return 2
    after = process.memory_info()._asdict()
    io_after = process.io_counters()._asdict()
    peak = after.get("peak_wset", after["rss"])
    private_peak = after.get("peak_pagefile")
    measurements = {
        "status": "COMPLETE_LOCAL_REAL_SESSION_ACCEPTED",
        "scope": preview["scope"], "preview_identity": preview["artifact_identity"],
        "elapsed_seconds": time.monotonic() - started,
        "memory_before": before, "memory_after": after,
        "peak_process_resident_bytes": peak,
        "peak_incremental_resident_bytes": max(0, peak - before["rss"]),
        "peak_incremental_private_bytes": None if private_peak is None else max(0, private_peak - before.get("private", before.get("pagefile", 0))),
        "measurement_method": "Windows OS process high-water counters; RSS and private commit reported independently",
        "resource_gate": gate,
        "io_counter_delta": {k: v - io_before[k] for k, v in io_after.items()},
        "actual_consumer_mismatch": None,
    }
    if measurements["peak_incremental_resident_bytes"] >= 1024**3 or (
        measurements["peak_incremental_private_bytes"] or 0) >= 1024**3:
        print(json.dumps({**measurements, "status": "REAL_SESSION_REPLAY_BLOCKED", "reason": "MEASURED_MEMORY_TARGET_EXCEEDED"}))
        return 2
    output.mkdir(parents=True, exist_ok=False)
    (output / "preview.json").write_text(json.dumps(preview, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (output / "preview.md").write_text(rendered, encoding="utf-8")
    (output / "measurements.json").write_text(json.dumps(measurements, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(measurements, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
