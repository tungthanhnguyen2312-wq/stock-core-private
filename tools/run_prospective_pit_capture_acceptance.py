"""Bounded offline capture acceptance over exact retained roots and hermetic tests.

Writes only the named report and scratch outputs. No Daily/provider/publication
run, retrospective companion, marker or T0 registration in the retained roots.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree
from datetime import date, timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import prospective_market_evidence_retention as old_retention
import prospective_market_snapshot_contract as market
import prospective_pit_capture as capture
import prospective_pit_capture_retention as store
from tools.run_market_only_pit_acceptance import run as legacy_acceptance
from test_production_call_shape_smoke import _offline_smoke_guard


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_benchmark(scratch, *, ticker_count=256, session_count=260):
    """Synthetic load fixture only; never written to a real evidence root."""
    from test_prospective_pit_capture import snapshot, receipt_for, presence, calendar
    from governed_session_chain import registered_outcome_horizons
    root = Path(scratch)
    root.mkdir(parents=True, exist_ok=True)
    if store.load_marker(root):
        raise ValueError("BENCHMARK_REQUIRES_NEW_SYNTHETIC_SCRATCH_ROOT")
    days, day = [], date(2026, 10, 5)
    # Fixture construction, never a runtime calendar fallback.
    while len(days) < session_count + max(registered_outcome_horizons()):
        if day.weekday() < 5:
            days.append(day.isoformat())
        day += timedelta(days=1)
    # Overlapping one-year-sized synthetic responses retain all historical depth.
    for window in (days[:250], days[120:]):
        old_retention.retain_working_dates_calendar(market.canonical({"workingDates": window}),
            retrieved_at=window[0]+"T01:00:00Z", documentation_sha256="a"*64,
            documentation_retrieved_at="2026-10-02T03:40:00Z", root=root)
    first_record = None
    for index, session in enumerate(days[:session_count]):
        rows = []
        for number in range(ticker_count):
            ticker = f"X{number:04d}"
            value = snapshot(session, ticker=ticker)
            receipt = receipt_for(value)
            receipt["receipt_id"] = market.sha256_hex(market.canonical([ticker, session, "SYNTHETIC_LOAD_ONLY"]))
            receipt = capture.identified(receipt, "prospective_market_receipt")
            source = value["records"][ticker]
            row = capture.capture_binding(receipt, source["observations"][0], source, source_snapshot_identity=value["snapshot_identity"],
                created_at=session+"T12:00:00Z", capture_window_close=capture.capture_window(session)[1], presence=presence(session, ticker=ticker))
            rows.append(row)
            if index == session_count-1:
                # Only current receipts are used by readiness. Historic fixtures
                # have compact bindings; no new file-per-observation history.
                old_retention._retain(root / "operations-review/prospective-market-evidence-v1" / session / "receipts" /
                                      (receipt["receipt_id"]+".json"), receipt)
        batch = capture.batch(capture.CAPTURE_CONTRACT, rows, session=session, created_at=session+"T12:00:00Z")
        ref = store._retain_batch(root, "bindings", batch)
        record = capture.identified({"contract_version": "prospective_capture_complete_session/v1", "session": session,
            "completion_known_at": session+"T12:05:00Z", "completion_gate_status": "READY", "completion_gate_identity": "SYNTHETIC_LOAD_ONLY",
            "capture_binding_identity": ref["artifact_identity"], "capture_binding": ref,
            "listing_presence_identity": "SYNTHETIC_LOAD_ONLY", "market_manifest_identity": "SYNTHETIC_LOAD_ONLY"},
            "prospective_capture_complete_session")
        old_retention._retain(root / store.STORE / "sessions" / (session+".json"), record)
        first_record = first_record or record
    marker = capture.identified({"contract_version": "first_complete_capture_session/v1", "session": days[0],
        "written_at": first_record["completion_known_at"], "capture_session_identity": first_record["artifact_identity"],
        "synthetic_load_only": True}, "first_complete_capture_session")
    old_retention._retain(root / store.STORE / "first_complete_capture_session.json", marker)
    started = time.perf_counter()
    evaluator = store.CaptureIndex(root, cutoff=days[session_count-1]+"T12:05:00Z")
    index_seconds = time.perf_counter()-started
    started = time.perf_counter()
    report = evaluator.readiness(session=days[session_count-1])
    evaluate_seconds = time.perf_counter()-started
    assert report["counts_at_depth"]["250"] == ticker_count
    assert report["status"] == "READY_FOR_BOUNDED_EVALUATION" and not report["evaluation_authorized"]
    assert report["performance"]["scans"] == {"capture_batches": min(250, session_count), "latest_receipts": ticker_count}
    assert all(len(rows) <= 250 for rows in evaluator.rows.values())
    import psutil
    mem = psutil.Process().memory_info()
    return {"scope": "SYNTHETIC_LOAD_ONLY_NOT_REAL_MARKET_EVIDENCE", "tickers": ticker_count, "sessions": session_count,
        "indexed_sessions_per_ticker": 250, "index_pairs": sum(len(v) for v in evaluator.rows.values()),
        "index_seconds": round(index_seconds, 6), "readiness_seconds": round(evaluate_seconds, 6),
        "process_peak_rss_bytes": getattr(mem, "peak_wset", mem.rss), "counts_at_depth": report["counts_at_depth"],
        "scan_counts": report["performance"]["scans"], "authority_effect": "NONE", "all_assertions_passed": True}


def _receipt_inventory(root):
    paths, identities = [], Counter()
    digest = hashlib.sha256()
    for path in sorted((Path(root) / "operations-review/prospective-market-evidence-v1").glob("*/receipts/*.json")):
        row = old_retention._verified(path)
        observation = row["observation"]
        if observation["trading_session"] >= capture.CAPTURE_START_NOT_BEFORE:
            raise ValueError("RETAINED_ACCEPTANCE_MUST_NOT_CREATE_OR_CONSUME_POST_RELEASE_CAPTURE")
        resolved = capture.effective_receipt(row, [], "2026-10-03T23:59:59Z")
        identities[resolved["capture_state"]] += 1
        paths.append(path)
        digest.update(market.canonical([path.relative_to(root).as_posix(), file_hash(path)]))
    return paths, dict(identities), digest.hexdigest()


def run(*, primary_root, raw_pit_root, calendar_root, protected, scratch, cutoff, run_tests=True):
    started = time.perf_counter()
    scratch = Path(scratch)
    scratch.mkdir(parents=True, exist_ok=True)
    source_roots = [Path(primary_root).resolve(), Path(raw_pit_root).resolve(), Path(calendar_root).resolve()]
    if any(scratch.resolve().is_relative_to(r / "operations-review") for r in source_roots):
        raise ValueError("ACCEPTANCE_SCRATCH_MUST_BE_SEPARATE_FROM_RETAINED_EVIDENCE")
    protected = {name: Path(path) for name, path in protected.items()}
    before = {name: {"sha256": file_hash(path), "bytes": path.stat().st_size} for name,path in protected.items()}
    # Exact modern T0 family only, no broad operations-review scan.
    t0_paths = sorted((Path(primary_root) / "operations-review/prospective-decision-retention-v1").glob("*/*/prospective_decision_snapshot.json"))
    t0_hashes = {p.relative_to(primary_root).as_posix(): file_hash(p) for p in t0_paths}
    baseline = json.loads((ROOT / "docs/internal/PIT_MINIMUM_VIABLE_EVIDENCE_CLOSURE_ACCEPTANCE.json").read_bytes())
    manifest = json.loads((ROOT / "docs/internal/R7_RETAINED_INPUT_MANIFEST.json").read_bytes())
    tests = {"status": "NOT_RUN"}
    with _offline_smoke_guard() as counters:
        receipts, receipt_counts, receipt_digest = _receipt_inventory(Path(primary_root))
        calendars = store.load_calendars(Path(calendar_root))
        old = legacy_acceptance(manifest=manifest, roots={"primary": Path(primary_root), "raw_pit": Path(raw_pit_root)},
            calendar_path=ROOT / "config/governed_trading_session_calendar_v1.json", calendar_receipts=calendars)
        if (old["signal_input_coverage"] != baseline["after"]["signal_input_coverage"] or
            old["gross_replay_input_coverage"] != baseline["after"]["gross_replay_input_coverage"] or
            old["inventory"] != baseline["inventory"]):
            raise ValueError("LEGACY_RETAINED_ELIGIBILITY_CHANGED")
        # Release has no fabricated new captures. Retained price sessions do not
        # advance this clock merely because calendar time has elapsed.
        index = store.CaptureIndex(primary_root, cutoff=cutoff)
        readiness = index.readiness(session="2026-10-02")
        if readiness["first_complete_capture_session"] is not None or readiness["complete_session_count"] or any(readiness["counts_at_depth"].values()):
            raise ValueError("RELEASE_MUST_NOT_BACKFILL_CAPTURE_CLOCK")
        if run_tests:
            import pytest
            junit = scratch / "capture-tests.xml"
            result = pytest.main([str(ROOT / "tests/test_prospective_pit_capture.py"), "-q", "--tb=short", "--junitxml=" + str(junit)])
            if result != 0:
                raise ValueError("CAPTURE_HERMETIC_ACCEPTANCE_FAILED")
            suites = ElementTree.parse(junit).getroot()
            cases = list(suites.iter("testcase"))
            tests = {"status": "PASS", "passed": len(cases), "failures": sum(len(list(c.iter("failure"))) for c in cases),
                     "errors": sum(len(list(c.iter("error"))) for c in cases), "skips": sum(len(list(c.iter("skipped"))) for c in cases)}
        after = {name: file_hash(path) for name,path in protected.items()}
        if any(after[name] != row["sha256"] for name,row in before.items()):
            raise ValueError("PROTECTED_PRODUCT_BYTES_CHANGED")
        after_receipts, after_counts, after_digest = _receipt_inventory(Path(primary_root))
        if after_receipts != receipts or after_counts != receipt_counts or after_digest != receipt_digest:
            raise ValueError("OLD_MARKET_RECEIPTS_CHANGED")
        if {p.relative_to(primary_root).as_posix(): file_hash(p) for p in t0_paths} != t0_hashes:
            raise ValueError("OLD_T0_BYTES_CHANGED")
        assert counters == {"network": 0, "provider": 0, "vnstock_import": 0}
    try:
        import psutil
        mem = psutil.Process().memory_info()
        peak = getattr(mem, "peak_wset", getattr(mem, "rss", None))
    except ImportError:
        peak = None
    body = {"contract_version": "prospective_pit_capture_offline_acceptance/v1",
        "disposition": "PROSPECTIVE_PIT_CAPTURE_COMPLETENESS_COMPLETE", "starting_main": "799f727d1d783cedcf5327ab8ff9a86478aa9096",
        "authority_effect": "NONE / CAPTURE_COMPLETENESS_ONLY", "hermetic_acceptance": tests,
        "retained_legacy_market_inventory": old["inventory"], "legacy_market_eligibility_exactly_unchanged": True,
        "legacy_signal_coverage": old["signal_input_coverage"], "legacy_gross_coverage": old["gross_replay_input_coverage"],
        "old_immutable_receipts": {"versions": len(receipts), "classification_counts": receipt_counts,
                                   "before_after_digest": receipt_digest, "bytes_unchanged": True},
        "protected_product_bytes": before, "protected_product_bytes_unchanged": True,
        "historical_t0": {"exact_retained_files": len(t0_paths), "source_hashes": t0_hashes, "bytes_unchanged": True,
                          "october_2": "UNAVAILABLE_NO_RETROSPECTIVE_SEAL", "writes": 0},
        "release_readiness": {k: readiness[k] for k in ("status", "first_complete_capture_session", "complete_session_count", "counts_at_depth",
            "session_chain_gaps", "legacy_incomplete_receipt_versions", "new_signals_declared", "evaluation_authorized")},
        "retained_calendar": {"receipts": len(calendars), "source_identities": [c["artifact_identity"] for c in calendars],
                              "window_start": min((c["window_start"] for c in calendars), default=None),
                              "window_end": max((c["window_end"] for c in calendars), default=None)},
        "network_provider_calls": counters, "additional_daily_provider_requests": 0, "canonical_publication_writes": 0,
        "first_real_acceptance": {"gate": "FIRST_REAL_POST_RELEASE_CAPTURE_ACCEPTANCE", "status": "PENDING",
            "release_waits_for_future_session": False},
        "future_ca_seam": readiness["future_ca_seam"], "performance": {"whole_acceptance_seconds": round(time.perf_counter()-started, 6),
            "process_peak_rss_bytes": peak, "normal_readiness": readiness["performance"], "one_index_per_run": True},
        "input_sha256": old["input_sha256"], "new_evaluation_signals": 0, "all_assertions_passed": True,
        "next_gate": "CONTEXTUAL_TECHNICAL_SEMANTIC_HARDENING_V2", "next_gate_started": False}
    return capture.identified(body, "prospective_pit_capture_offline_acceptance")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("primary-root", "raw-pit-root", "calendar-root", "scratch", "report"):
        parser.add_argument("--" + arg, type=Path, required=True)
    parser.add_argument("--protected", action="append", default=[], help="Exact label=path; no source directory search.")
    parser.add_argument("--cutoff", required=True)
    args = parser.parse_args()
    protected = dict(item.split("=", 1) for item in args.protected)
    report = run(primary_root=args.primary_root, raw_pit_root=args.raw_pit_root, calendar_root=args.calendar_root,
        protected=protected, scratch=args.scratch, cutoff=args.cutoff)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"disposition": report["disposition"], "readiness": report["release_readiness"], "performance": report["performance"]}), flush=True)


if __name__ == "__main__":
    main()
