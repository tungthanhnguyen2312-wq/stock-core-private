"""Offline October-2 acceptance using explicit retained paths, bounded record parsing.

No acquisition or canonical/T0 write. Large price/decision corpora are parsed
once per record, with their standing canonical content hashes verified in-stream.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import canonical_market_bars as bars
import contextual_technical_features as features
import daily_session_level2_package as level2
import stocklookup_core.decision.integrated_investment_decision_product as product
import market_wide_historical_research_context as history
import prospective_decision_retention as retention
from field_temporal_contract import _sanitize_for_json
from test_production_call_shape_smoke import _offline_smoke_guard


from bounded_artifact_stream import ObjectStream, source_hash, header, stream_artifact


def summarize(records, denominator):
    coverage = features.coverage(records)
    absent = denominator - len(records)
    for tf in features.TIMEFRAMES:
        coverage[tf]["price_basis"]["OUT_OF_CURRENT_RESEARCH_SCOPE"] = absent
        for family in features.FAMILIES:
            stats = coverage[tf]["families"][family]
            stats["status_counts"]["NOT_APPLICABLE_OUT_OF_SCOPE"] = absent
            stats["primary_blockers"]["OUT_OF_CURRENT_RESEARCH_SCOPE"] = absent
    return coverage


def representative_cases(records):
    predicates = {
        "strong_trend": lambda r: r["features"]["interpretation"].get("values", {}).get("repair_context") == "MATURE_TREND",
        "range_base": lambda r: r["features"]["base"].get("values", {}).get("state") == "ESTABLISHED",
        "early_repair": lambda r: r["features"]["interpretation"].get("values", {}).get("repair_context") in {"EARLY_REPAIR", "REVERSAL_ATTEMPT"},
        "deterioration": lambda r: r["features"]["interpretation"].get("values", {}).get("repair_context") in {"CONTINUING_DETERIORATION", "DETERIORATION_AFTER_EXTENSION"},
        "insufficient_history": lambda r: r["features"]["structure"]["status"] == "INSUFFICIENT_HISTORY",
        "ca_blocker": lambda r: any(f["status"] == "BLOCKED_CA_COMPARABILITY" for f in r["features"].values()),
    }
    cases = {}
    for name, predicate in predicates.items():
        matches = []
        for ticker, record in sorted(records.items()):
            frame = record["contextual_technical"]["timeframes"]["1D"]
            # Missing feature values are explicit null, not empty evidence.
            safe = {**frame, "features": {k: {**v, "values": v["values"] or {}} for k, v in frame["features"].items()}}
            if predicate(safe): matches.append(ticker)
        ticker = matches[0] if matches else None
        cases[name] = {"selection": "FIRST_LEXICOGRAPHIC_MATCH_NO_OUTCOME_FILTER", "match_count": len(matches),
                       "ticker": ticker, "context": records[ticker]["contextual_technical"] if ticker else None,
                       "status": "REAL_RETAINED_CASE" if ticker else "NO_REAL_RETAINED_MATCH"}
    matches = [t for t, r in sorted(records.items()) if r["contextual_technical"]["multi_timeframe"]["state"] == "MIXED_DIVERGENT"]
    ticker = matches[0] if matches else None
    cases["D_W_M_disagreement"] = {"selection": "FIRST_LEXICOGRAPHIC_MATCH_NO_OUTCOME_FILTER", "match_count": len(matches),
        "ticker": ticker, "context": records[ticker]["contextual_technical"] if ticker else None,
        "status": "REAL_RETAINED_CASE" if ticker else "NO_REAL_RETAINED_MATCH_W_M_LOOKBACK_BLOCKERS_PRESERVED"}
    return cases


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--session", default="2026-10-02")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--feature-output", type=Path, required=True)
    args = parser.parse_args(argv)
    paths = level2.session_artifact_paths(args.source_root, args.session)
    paths = {k: paths[k] for k in ("exact_session_snapshot", "universe_resolution", "technical_recovery")}
    paths["input_registry"] = args.source_root / "config/daily_research_session_input_registry.json"
    registry = json.loads(paths["input_registry"].read_text(encoding="utf-8"))
    event_binding = registry["sessions"][args.session]["event_context"]
    paths["events"] = args.source_root / event_binding["path"]
    paths["decision"] = args.source_root / "operations-review/canonical-post-close-v1" / args.session / "enrichment/integrated_investment_decision_product.json"
    paths["calendar"] = ROOT / "config/governed_trading_session_calendar_v1.json"
    # Only separately chosen acceptance outputs may be written, never canonical evidence.
    if args.output.resolve() == args.feature_output.resolve() or any(
            destination.resolve() == source.resolve() or args.source_root.resolve() / "operations-review" in destination.resolve().parents
            for destination in (args.output, args.feature_output) for source in paths.values()):
        raise ValueError("ACCEPTANCE_OUTPUT_MUST_NOT_REPLACE_RETAINED_EVIDENCE")
    before = {k: source_hash(v) for k, v in paths.items()}
    start = time.perf_counter()
    with _offline_smoke_guard() as counters:
        universe = json.loads(paths["universe_resolution"].read_text(encoding="utf-8"))
        history._verify_hashed_identity(universe, label="UNIVERSE")
        recovery = json.loads(paths["technical_recovery"].read_text(encoding="utf-8"))
        history._verify_hashed_identity(recovery, label="RECOVERY")
        snapshot_header = header(paths["exact_session_snapshot"])
        cutoff = snapshot_header["requested_at"]
        if snapshot_header["resolved_completed_session"] != args.session:
            raise ValueError("ACCEPTANCE_SESSION_MISMATCH")
        if recovery["source_lineage"]["p3f9b_snapshot_identity"] != snapshot_header["snapshot_identity"]:
            raise ValueError("ACCEPTANCE_RECOVERY_SOURCE_MISMATCH")
        calendar = bars.governed_calendar_projection(json.loads(paths["calendar"].read_text(encoding="utf-8")))
        event_artifact = json.loads(paths["events"].read_text(encoding="utf-8"))
        import current_official_event_context as event_module
        assert all(event_artifact.get(k) == v for k, v in event_module._identity(event_artifact).items())
        assert event_artifact["artifact_identity"] == event_binding["artifact_identity"]
        events = defaultdict(list)
        for record in event_artifact["records"].values():
            for event in record.get("events", []): events[event["ticker"]].append(event)
        records, all_tickers = {}, set()
        args.feature_output.parent.mkdir(parents=True, exist_ok=True)
        with args.feature_output.open("wb") as output:
            def price_record(ticker, row):
                all_tickers.add(ticker)
                ur = universe["records"][ticker]
                if ur["activity_and_session_state"] in history.IN_SCOPE_ACTIVITY_STATES:
                    override = recovery.get("recovered_history_overrides", {}).get(ticker, {})
                    recovered = override.get("state") == "RECOVERED_COMPLETE_TECHNICAL_HISTORY"
                    observations = override.get("observations", []) if recovered else row.get("observations", [])
                    record = features.build_research_projections(observations, ticker=ticker, target_session=args.session,
                        knowledge_cutoff=cutoff, source_identity=recovery["artifact_identity"] if recovered else snapshot_header["snapshot_identity"],
                        calendar_evidence=calendar, ca_events=events[ticker])
                    records[ticker] = record
                    for chunk in retention._json_bytes({"ticker": ticker, **record}): output.write(chunk)
                    output.write(b"\n")
                if len(all_tickers) % 100 == 0: print("FEATURES", len(all_tickers), flush=True)
            price_metadata, price_digest, price_count = stream_artifact(paths["exact_session_snapshot"],
                excluded={"snapshot_identity", "snapshot_sha256"}, on_record=price_record, sanitize=True)
        assert price_digest == snapshot_header["snapshot_sha256"] == price_metadata["snapshot_sha256"]
        assert price_metadata["requested_at"] == cutoff and price_metadata["snapshot_identity"] == snapshot_header["snapshot_identity"]
        assert all_tickers == set(universe["records"])
        feature_seconds = time.perf_counter() - start
        parent = {"contract_version": history.CONTRACT_VERSION, "session": args.session, "records": records}
        parent.update(history.content_identity(parent))
        verified_bars = product.market_bar_context_records(parent, session=args.session, requested_at=cutoff)
        verified = features.verified_context_records(parent, session=args.session,
            knowledge_cutoff=cutoff, verified_bar_contexts=verified_bars)
        assert all(v["status"] == "AVAILABLE" for v in verified.values())
        decisions, deltas, posture_counts = set(), 0, Counter()
        decision_digest = hashlib.sha256()
        def decision_record(ticker, row):
            nonlocal deltas
            decisions.add(ticker)
            assert row["as_of_session"] == args.session
            before_record = copy.deepcopy(row)
            before_identity = product.decision_identity(row)
            if ticker in verified:
                product.attach_contextual_technical(row, verified[ticker])
                assert product.decision_identity(row) == before_identity == row["decision_identity"]
                row.pop("contextual_technical_context")
                row["evidence_axes"]["TACTICAL_STRUCTURE"].pop("contextual_feature_reference")
            deltas += row != before_record
            posture_counts[row["research_action_posture"]] += 1
            decision_digest.update(features.market.canonical([ticker, before_identity, row["research_action_posture"], row.get("trigger"), row.get("invalidation"), row.get("portfolio_fit")]))
            if len(decisions) % 200 == 0: print("DECISION_PARITY", len(decisions), flush=True)
        decision_metadata, decision_hash, decision_count = stream_artifact(paths["decision"],
            excluded=product._IDENTITY_EXCLUDED, on_record=decision_record)
        assert decision_hash == decision_metadata["artifact_sha256"]
        assert decision_metadata["artifact_identity"] == product.CONTRACT_VERSION+":"+decision_hash
        assert decisions == all_tickers and deltas == 0
        after = {k: source_hash(v) for k, v in paths.items()}
        assert before == after
        try:
            import psutil
            peak = getattr(psutil.Process().memory_info(), "peak_wset", None)
        except ImportError:
            peak = None
        report = {"contract_version": "contextual_technical_retained_acceptance/v1", "feature_contract": features.CONTRACT_VERSION,
            "starting_main": "66735a3f5df3e028bd0a2b0d9840d9caa8a91ade", "session": args.session,
            "knowledge_cutoff": cutoff, "universe_denominator": price_count, "current_research_scope": len(records),
            "coverage": summarize(records, price_count), "representative_cases": representative_cases(records),
            "source_hashes": before, "source_identities": {"price": price_metadata["snapshot_identity"], "decision": decision_metadata["artifact_identity"],
                "universe": universe["artifact_identity"], "recovery": recovery["artifact_identity"],
                "events": event_artifact["artifact_identity"]},
            "input_hashes_unchanged": True, "feature_batch_sha256": source_hash(args.feature_output),
            "before_after": {"cohort": decision_count, "denominator_unchanged": True, "exact_adapter_records": len(verified),
                "decision_field_deltas": deltas, "posture_counts": dict(sorted(posture_counts.items())),
                "policy_trigger_invalidation_portfolio_authority_deltas": 0, "decision_identity_deltas": 0,
                "comparison_digest": decision_digest.hexdigest(), "product_content_identity": "ADDITIVE_CHANGE_UNDER_STANDING_CONTRACT",
                "scope": "FULL_EXACT_RETAINED_COHORT_NORMAL_PRODUCT_ADAPTER_NO_FINANCIAL_REBUILD"},
            "performance": {"feature_build_seconds": round(feature_seconds,6), "whole_acceptance_seconds": round(time.perf_counter()-start,6),
                "process_lifetime_peak_rss_bytes": peak, "price_corpora_parsed": 1, "decision_corpora_parsed": 1,
                "json_member_buffer_limit_bytes": 16*1024*1024},
            "network_provider_calls": counters, "t0_writes": 0, "canonical_publication_writes": 0,
            "tests": "Focused and required Producer CI recorded in the accompanying contract at release",
            "authority_effect": features.AUTHORITY_EFFECT, "all_assertions_passed": True}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("wb") as output:
            for chunk in retention._json_bytes(report, pretty=True): output.write(chunk)
    print(json.dumps({"universe": price_count, "scope": len(records), "deltas": deltas, "performance": report["performance"]}), flush=True)


if __name__ == "__main__":
    main()
