"""Read-only, identical-cohort acceptance over pinned Financial V2 evidence.

Baseline is an actual pre-change engine artifact, never a fabricated old publication.
The unchanged peer owner is restricted to its original feature inventory for baseline.
Writes are confined to a new explicit output directory outside the retained input root.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import canonical_daily_financial_v2_materialization as material
from ai_research_session_delivery import project_integrated_decision_for_ai_delivery
from stocklookup_core.decision import integrated_investment_decision_product as decision
from stocklookup_core.financial import financial_analysis_engine_v2 as engine
from stocklookup_core.financial import financial_analysis_product_projection as projection
from stocklookup_core.financial import financial_v2_current_input_authority as authority_owner
from stocklookup_core.valuation import current_research_valuation_context as valuation
from tools.replay_vn30_financial_valuation_research_scaleout import retained_cohort

NEW = tuple(engine.EXTENDED_RATIO_HISTORY_INPUTS)
BASELINE_PEERS = tuple(fid for fid in valuation.ENGINE_PEER_FEATURES if fid not in NEW)


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def peer_reasons(metric):
    reason = metric.get("reason") or []
    return reason if isinstance(reason, list) else [reason]


def summarize(artifact, peers, contexts):
    records = artifact["records"]
    return {fid: {
        "underlying_feature_fitness": dict(sorted(Counter(r["features"][fid]["fitness"] for r in records.values()).items())),
        "underlying_blocked_reasons": dict(sorted(Counter(code for r in records.values()
            for code in r["features"][fid].get("reason_codes", [])).items())),
        "history": dict(sorted(Counter(r["history_context"].get(fid, {}).get("status", "NOT_IMPLEMENTED") for r in records.values()).items())),
        "peer_status": dict(sorted(Counter(peers[t].get(fid, {}).get("status", "NOT_IMPLEMENTED") for t in records).items())),
        "peer_reasons": dict(sorted(Counter(str(code) for t in records
            for code in peer_reasons(peers[t].get(fid, {}))).items())),
        "decision_usable_comparisons": sum(contexts[t]["metrics"].get(fid, {}).get("status") == "READY_RESEARCH_ONLY" for t in records),
        "decision_status": dict(sorted(Counter(contexts[t]["metrics"].get(fid, {}).get("status", "NOT_IMPLEMENTED") for t in records).items())),
        "decision_history_status": dict(sorted(Counter((contexts[t]["metrics"].get(fid, {}).get("own_history_context") or {}).get("status", "NOT_IMPLEMENTED") for t in records).items())),
        "decision_blockers": dict(sorted(Counter(code for t in records
            for code in contexts[t]["metrics"].get(fid, {}).get("consumer_blocker_reason_codes", [])).items())),
    } for fid in NEW}


def session_views(artifact, root, session, *, baseline=False):
    wrapper = material.build_session_artifact(root=root, decision_session=session,
        product_tickers=sorted(artifact["records"]), requested_at="2026-10-18T00:00:00+07:00", engine_artifact=artifact)
    if baseline:
        wrapper["engine_fundamental_peer_context"] = {
            t: {fid: value for fid, value in metrics.items() if fid in BASELINE_PEERS}
            for t, metrics in wrapper["engine_fundamental_peer_context"].items()}
        wrapper.update(material._identity(wrapper))
    compact = wrapper["financial_analysis_product"]
    contexts = projection.financial_peer_contexts(materialization=wrapper, product=compact, session=session)
    return wrapper, compact, contexts


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--retained-root", required=True, type=Path)
    p.add_argument("--baseline-engine", required=True, type=Path)
    p.add_argument("--candidate-engine", type=Path, help="Reuse a content-verified engine saved by an earlier acceptance attempt.")
    p.add_argument("--session", required=True)
    p.add_argument("--membership-artifact", type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args(argv)
    root, output = args.retained_root.resolve(), args.output.resolve()
    if output == root or root in output.parents or output.exists():
        raise ValueError("OUTPUT_MUST_BE_NEW_AND_OUTSIDE_RETAINED_ROOT")
    authority = authority_owner.resolve(root)
    inputs = [args.baseline_engine.resolve(), authority.semantics_artifact_path, authority.semantics_facts_path,
        authority.feature_store_artifact_path, authority.feature_store_records_path, authority.classification_diagnostics_path]
    if authority.industry_snapshot_path.is_file():
        inputs.append(authority.industry_snapshot_path)
    if args.membership_artifact:
        inputs.append(args.membership_artifact.resolve())
    if args.candidate_engine:
        inputs.append(args.candidate_engine.resolve())
    if any(output == path or output in path.parents or output == path.parent for path in inputs):
        raise ValueError("OUTPUT_OVERLAPS_INPUTS")
    hashes = {str(path): sha(path) for path in inputs}
    baseline = json.loads(args.baseline_engine.read_text(encoding="utf8"))
    if baseline.get("artifact_identity") != engine.content_identity(baseline)["artifact_identity"]:
        raise ValueError("BASELINE_ENGINE_IDENTITY_MISMATCH")
    if baseline.get("schema_version") != "2.3.0" or any(
            set(NEW) & set(r["history_context"]) for r in baseline["records"].values()):
        raise ValueError("BASELINE_MUST_PREDATE_RATIO_HISTORY_EXPANSION")
    if args.candidate_engine:
        with gzip.open(args.candidate_engine, "rt", encoding="utf8") as handle:
            after = json.load(handle)
        if after.get("artifact_identity") != engine.content_identity(after)["artifact_identity"]:
            raise ValueError("CANDIDATE_ENGINE_IDENTITY_MISMATCH")
    else:
        after = material.build_engine_artifact(root=root, requested_at="2026-10-18T00:00:00+07:00", authority=authority)
    assert baseline["source_identities"] == after["source_identities"]
    assert set(baseline["records"]) == set(after["records"])
    for ticker, old in baseline["records"].items():
        new = after["records"][ticker]
        assert old["features"] == new["features"], ticker
        assert {k:v for k,v in old.items() if k != "history_context"} == {k:v for k,v in new.items() if k != "history_context"}, ticker
        assert old["history_context"] == {k:v for k,v in new["history_context"].items() if k not in NEW}, ticker
    output.mkdir(parents=True)
    with gzip.open(output / "candidate-engine.json.gz", "wt", encoding="utf8") as handle:
        json.dump(after, handle, ensure_ascii=True)
    before_wrapper, before_compact, before_contexts = session_views(baseline, root, args.session, baseline=True)
    after_wrapper, after_compact, after_contexts = session_views(after, root, args.session)
    before_peers, after_peers = before_wrapper["engine_fundamental_peer_context"], after_wrapper["engine_fundamental_peer_context"]
    for ticker in before_peers:
        assert before_peers[ticker] == {k:v for k,v in after_peers[ticker].items() if k in BASELINE_PEERS}
    membership = retained_cohort(args.membership_artifact, args.session) if args.membership_artifact else None
    members = set(membership["tickers"]) if membership else set()
    delivered_counts, outside_counts, delivered_history = Counter(), Counter(), Counter()
    peer_tickers, history_tickers = set(), set()
    with gzip.open(output / "comparison-records.jsonl.gz", "wt", encoding="utf8") as handle:
        for ticker in sorted(after["records"]):
            results = []
            for compact, contexts in ((before_compact, before_contexts), (after_compact, after_contexts)):
                results.append(decision.build_ticker_integrated_decision(ticker=ticker, as_of_session=args.session,
                    tactical_record=None, financial_record=compact["records"][ticker], valuation_record=None,
                    relative_volume_record=None, market_sector_record=None, financial_peer_context=contexts[ticker]))
            for field in ("research_action_posture", "fundamental_state", "fundamental_support"):
                assert results[0][field] == results[1][field], (ticker, field)
            # New analysis legitimately changes the engine content identity. Signals
            # carry that binding even though values, fitness and policy are unchanged.
            normalized = json.dumps(results[0]["fundamental_synthesis"], sort_keys=True).replace(
                baseline["artifact_identity"], after["artifact_identity"])
            assert json.loads(normalized) == results[1]["fundamental_synthesis"], (ticker, "synthesis_except_engine_binding")
            delivered = project_integrated_decision_for_ai_delivery(results[1])
            assert delivered["financial_peer_context"] == after_contexts[ticker]
            assert delivered["current_research_decision_input"]["dimensions"]["FUNDAMENTAL"]["financial_peer_context"] == after_contexts[ticker]
            for fid in NEW:
                metric = delivered["financial_peer_context"]["metrics"][fid]
                history = after["records"][ticker]["history_context"][fid]
                delivered_own_history = metric["own_history_context"]
                if metric["freshness"]["freshness_status"] == "UNAVAILABLE" and history["status"] in ("AVAILABLE", "PARTIAL", "INSUFFICIENT_HISTORY"):
                    assert delivered_own_history["status"] == "UNAVAILABLE" and "subject_value" not in delivered_own_history
                else:
                    assert delivered_own_history == history
                if delivered_own_history["status"] in ("AVAILABLE", "PARTIAL"):
                    delivered_history[fid] += 1
                    history_tickers.add(ticker)
                if metric["status"] == "READY_RESEARCH_ONLY":
                    delivered_counts[fid] += 1
                    peer_tickers.add(ticker)
                    if members and ticker not in members:
                        outside_counts[fid] += 1
                    assert metric["subject_value"] == after["records"][ticker]["features"][fid]["value"]
            handle.write(json.dumps({"ticker": ticker, "issuer_type": after["records"][ticker]["issuer_type"],
                "before": {fid: {"history": baseline["records"][ticker]["history_context"].get(fid),
                    "peer": before_contexts[ticker]["metrics"].get(fid)} for fid in NEW},
                "after": {fid: {"history": after["records"][ticker]["history_context"][fid],
                    "peer": after_contexts[ticker]["metrics"][fid]} for fid in NEW}}, ensure_ascii=True) + "\n")
    for path in inputs:
        assert sha(path) == hashes[str(path)], path
    summary = {"session": args.session, "cohort_count": len(after["records"]),
        "cohort_semantics": "PINNED_FINANCIAL_EVIDENCE_UNIVERSE_NOT_CURRENT_EXCHANGE_MEMBERSHIP",
        "baseline_engine_identity": baseline["artifact_identity"], "after_engine_identity": after["artifact_identity"],
        "source_identities": after["source_identities"], "input_hashes_unchanged": hashes,
        "baseline": summarize(baseline, before_peers, before_contexts), "result": summarize(after, after_peers, after_contexts),
        "ai_delivered_comparisons": dict(delivered_counts), "outside_retained_vn30_comparisons": dict(outside_counts),
        "ai_delivered_history": dict(delivered_history), "unique_peer_tickers": len(peer_tickers),
        "unique_history_tickers": len(history_tickers),
        "unique_peer_tickers_outside_retained_vn30": len(peer_tickers - members) if members else None,
        "membership": membership, "source_feature_objects_unchanged": True, "old_history_and_peers_unchanged": True,
        "posture_and_fundamental_policy_unchanged": True, "new_metric_input_coverage": 0,
        "acceptance_mode": "ISOLATED_FINANCIAL_DECISION_JOIN_NOT_A_REPLAYED_OR_REWRITTEN_SEALED_SESSION",
        "authority_promoted": False, "daily_or_runtime_write": False}
    (output / "acceptance.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf8")
    print(json.dumps({"cohort": len(after["records"]), "ai_comparisons": dict(delivered_counts),
        "outside_retained_vn30": dict(outside_counts), "identity": after["artifact_identity"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
