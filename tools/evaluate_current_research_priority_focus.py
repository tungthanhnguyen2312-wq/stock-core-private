"""Read-only retained evaluation of the research-focus projection.

Writes only a new directory outside the source tree and the retained evidence root.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stocklookup_core.decision import bounded_research_preview as bounded
from stocklookup_core.decision import current_research_priority_focus as focus


def _examples(rows, predicate, limit=3):
    found = [row for row in rows if predicate(row)]
    return {"count": len(found), "examples": [
        {"ticker": row["ticker"], "primary_lane": row.get("primary_lane"),
         "research_priority_tier": row.get("research_priority_tier"),
         "research_action_posture": row.get("research_action_posture"),
         "evolution": row.get("evolution"), "tactical_phase": row.get("tactical_phase"),
         "fundamental_state": row.get("fundamental_state"), "valuation_status": row.get("valuation_status"),
         "deep_dossier": row.get("deep_dossier"), "blocker": row.get("blocker")}
        for row in found[:limit]]}


def _evaluation(report):
    rows = report["overview"]
    dossiers = {item["ticker"]: item for item in report["dossiers"]}
    constructive = {"BREAKOUT_SETUP", "BREAKOUT_CONFIRMED", "EARLY_REVERSAL", "BASE_BUILDING", "BASE"}
    cases = {
        "early_reversal": _examples(rows, lambda row: row.get("primary_lane") == "EARLY_REVERSAL"),
        "forming_base": _examples(rows, lambda row: row.get("primary_lane") == "BASE_ACCUMULATION" or row.get("tactical_phase") in {"BASE_BUILDING", "BASE"}),
        "breakout_candidate": _examples(rows, lambda row: row.get("primary_lane") == "BREAKOUT" and row.get("tactical_phase") != "BREAKOUT_CONFIRMED"),
        "improving_setup": _examples(rows, lambda row: row.get("evolution") == "IMPROVING_CANDIDATE"),
        "failed_or_weakening": _examples(rows, lambda row: row.get("evolution") == "INVALIDATED_OR_WEAKENING"),
        "priority_now_not_action_ready": _examples(rows, lambda row: row.get("research_priority_tier") == "PRIORITY_NOW" and row.get("research_action_posture") in {"WAIT_FOR_CONFIRMATION", "EARLY_WATCH"}),
        "tactical_constructive_fundamental_insufficient": _examples(rows, lambda row: row.get("tactical_phase") in constructive and row.get("fundamental_state") in {None, "INSUFFICIENT"}),
        "valuation_available": _examples(rows, lambda row: row.get("valuation_status") == "AVAILABLE"),
        "valuation_not_available": _examples(rows, lambda row: row.get("valuation_status") != "AVAILABLE"),
    }
    rendered = []
    for ticker, dossier in dossiers.items():
        kinds = [item.get("kind") for item in dossier.get("relationships") or []]
        rendered.append({
            "ticker": ticker, "primary_lane": dossier.get("primary_lane"),
            "evolution": (dossier.get("evolution") or {}).get("code"),
            "posture": (dossier.get("summary") or {}).get("research_action_posture"),
            "transition": (dossier.get("setup_transition") or {}).get("governed_transition_label"),
            "relationship_kinds": kinds,
            "why_inspect": (dossier.get("summary") or {}).get("why_inspect"),
            "questions": [item.get("source_code") for item in (dossier.get("research_questions") or [])[:4]],
        })
    return {
        "status": report["status"], "session": report["session"],
        "previous_qualified_session": report["previous_qualified_session"],
        "selection_authority": report["selection_authority"],
        "selection_blocker": report["selection_blocker"],
        "population": report["population"],
        "qualified_count_lane_sum": report["qualified_count"],
        "unique_qualified_ticker_count": report.get("unique_qualified_ticker_count"),
        "selected_count": report["selected_count"],
        "lane_reports": report["lane_reports"],
        "overlap_count": len(report["overlaps"]),
        "cap_excluded_count": len(report["cap_excluded"]),
        "identity_mismatch_count": len(report["identity_mismatches"]),
        "identity_mismatch_statuses": sorted({item["status"] for item in report["identity_mismatches"]}),
        "statistics": report["statistics"],
        "priority_lineage": report.get("priority_lineage"),
        "verification_passes": report["verification_passes"],
        "cases": cases,
        "rendered_dossiers": rendered,
        "coverage_is_not_attractiveness": True,
        "comparison_to_explicit_preview": {
            "before": "The released preview renders only tickers a person already named. It does not discover a lane, preserve queue order, or join the queue record identity.",
            "after": "This projection selects from the retained daily opportunity queue, keeps each lane's source order, binds the queue record to the integrated decision, and writes support, contradiction, uncertainty, confirmation and research questions without a vote.",
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--current-operation", type=Path, required=True)
    parser.add_argument("--previous-operation", type=Path)
    parser.add_argument("--lanes", nargs="+", default=list(focus.DEFAULT_LANES))
    parser.add_argument("--tiers", nargs="+", default=list(focus.DEFAULT_TIERS))
    parser.add_argument("--max-tickers", type=int, default=8)
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
        report = focus.evaluate_research_focus(
            repo_root=args.evidence_root, session=args.session,
            current_operation=args.current_operation, previous_operation=args.previous_operation,
            lanes=tuple(args.lanes), tiers=tuple(args.tiers), max_tickers=args.max_tickers)
        rendered = focus.render_markdown(report)
    except (focus.ResearchFocusError, ValueError, OSError) as exc:
        print(json.dumps({"status": "REAL_SESSION_REPLAY_BLOCKED", "reason": str(exc),
                          "elapsed_seconds": time.monotonic() - started}, ensure_ascii=False))
        return 2
    after = process.memory_info()._asdict()
    io_after = process.io_counters()._asdict()
    peak = after.get("peak_wset", after["rss"])
    private_peak = after.get("peak_pagefile")
    measurements = {
        "status": "MEASURED",
        "report_status": report["status"],
        "artifact_identity": report["artifact_identity"],
        "elapsed_seconds": time.monotonic() - started,
        "memory_before": before, "memory_after": after,
        "peak_process_resident_bytes": peak,
        "peak_incremental_resident_bytes": max(0, peak - before["rss"]),
        "peak_incremental_private_bytes": None if private_peak is None else max(0, private_peak - before.get("private", before.get("pagefile", 0))),
        "measurement_method": "Windows OS process high-water counters; RSS and private commit reported independently",
        "resource_gate": gate,
        "io_counter_delta": {key: value - io_before[key] for key, value in io_after.items()},
        "verification_passes": report["verification_passes"],
        "selected_count": report["selected_count"],
        "unique_qualified_ticker_count": report.get("unique_qualified_ticker_count"),
    }
    if measurements["peak_incremental_resident_bytes"] >= 1024**3 or (
            measurements["peak_incremental_private_bytes"] or 0) >= 1024**3:
        print(json.dumps({**measurements, "status": "REAL_SESSION_REPLAY_BLOCKED", "reason": "MEASURED_MEMORY_TARGET_EXCEEDED"}))
        return 2
    output.mkdir(parents=True, exist_ok=False)
    report_text = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    markdown = rendered
    (output / "research_focus.json").write_text(report_text, encoding="utf-8")
    (output / "research_focus.md").write_text(markdown, encoding="utf-8")
    measurements["rendered_json_bytes"] = len(report_text.encode("utf-8"))
    measurements["rendered_markdown_bytes"] = len(markdown.encode("utf-8"))
    (output / "measurements.json").write_text(json.dumps(measurements, indent=2) + "\n", encoding="utf-8")
    (output / "evaluation_summary.json").write_text(
        json.dumps(_evaluation(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(measurements, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
