"""Build the separate retained-only volume/flow context and portable acceptance.

No Daily rerun, acquisition, canonical publication or historical T0 mutation.
Explicit roots and outputs make the same adapter usable for owner research.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"tests"))

import integrated_investment_decision_product as decision
import volume_and_flow_context as context
from volume_and_flow_retained import collect
from bounded_artifact_stream import source_hash, stream_artifact
from flow_price_divergence_shadow import write_immutable
from test_production_call_shape_smoke import _offline_smoke_guard


def starting_coherence_evaluator():
    """Replay exactly the two changed descriptive vocabulary branches, no policy."""
    source=inspect.getsource(decision.evaluate_evidence_axis_coherence)
    source=source.replace('    elif sector_state not in _KNOWN_SECTOR_STATES:\n        state = EVIDENCE_AXIS_COHERENCE_PARTIALLY_ALIGNED\n        reasons.append("SECTOR_LEADERSHIP_UNKNOWN_OR_DATA_LIMITED")\n','')
    namespace=dict(vars(decision))
    namespace['_WEAK_SECTOR_STATES']=frozenset({'LAGGING','WEAK','DETERIORATING'})
    exec(compile(source,'starting_descriptive_coherence','exec'),namespace)
    return namespace['evaluate_evidence_axis_coherence']


def coverage(artifact):
    items=[i for r in artifact["records"].values() for i in r["items"]]
    volume={}
    for tf in ("1D","1W","1M"):
        for horizon in (tf,tf+"/5",tf+"/20"):
            selected=[i for i in items if i["domain"]=="VOLUME" and i["horizon"]==horizon]
            volume[horizon]={"total_denominator":artifact["universe_denominator"],"in_scope_denominator":len(selected),
                "usable":sum(i["status"] in context.USABLE for i in selected),
                "current_usable":sum(i["status"] in context.USABLE and i["freshness"]=="CURRENT_SESSION" for i in selected),
                "status_counts":dict(sorted(Counter(i["status"] for i in selected).items())),
                "reason_counts":dict(sorted(Counter(code for i in selected for code in i["reason_codes"]).items())),
                "native_unit_counts":dict(sorted(Counter(i["unit_semantics"]["native"] for i in selected).items())),
                "outside_current_research_scope":artifact["universe_denominator"]-len(selected)}
    foreign={}
    for size in context.FLOW_WINDOWS:
        selected=[i for i in items if i["participant"]=="FOREIGN" and i["required_observations"]==size]
        cohort=[i for i in selected if i["coverage_scope"]["in_cohort"]]
        foreign[str(size)]={"universe_denominator":len(selected),"observed_cohort_denominator":len(cohort),
            "current_usable":sum(i["status"] in context.USABLE and i["freshness"]=="CURRENT_SESSION" for i in cohort),
            "mature":sum(i["status"] in context.USABLE for i in cohort),
            "cohort_status_counts":dict(sorted(Counter(i["status"] for i in cohort).items())),
            "outside_cohort_count":len(selected)-len(cohort)}
    return {"volume":volume,"foreign":foreign,"other_participants":{p:{"qualified":0,
        "unavailable":sum(i["participant"]==p and i["status"]=="UNAVAILABLE" for i in items),
        "reason":"SOURCE_NOT_QUALIFIED"} for p in context.PARTICIPANTS[1:]},
        "knowledge_stage_counts":dict(sorted(Counter(i["knowledge_stage"] for i in items).items()))}


def representative_cases(artifact):
    predicates={
        "high_relative_volume":lambda i:i["sub_domain"]=="NATIVE_VOLUME_REFERENCE" and i["horizon"]=="1D" and i["observed_state"]=="EXPANSION",
        "low_relative_volume":lambda i:i["sub_domain"]=="NATIVE_VOLUME_REFERENCE" and i["horizon"]=="1D" and i["observed_state"]=="CONTRACTION",
        "improving_volume_persistence":lambda i:i["sub_domain"]=="RELATIVE_VOLUME_PERSISTENCE" and i["observed_state"]=="RISING",
        "breakout_strong_participation":lambda i:(i.get("technical_relationship") or {}).get("breakout")=="BREAKOUT" and i["observed_state"]=="EXPANSION",
        "breakout_weak_participation":lambda i:(i.get("technical_relationship") or {}).get("breakout")=="BREAKOUT" and i["observed_state"]=="CONTRACTION",
        "base_repair_improving":lambda i:i["observed_state"]=="RISING" and ((i.get("technical_relationship") or {}).get("base")=="ESTABLISHED" or (i.get("technical_relationship") or {}).get("repair") in {"EARLY_REPAIR","REVERSAL_ATTEMPT"}),
        "persistent_foreign_sell_price_resilience":lambda i:(i.get("technical_relationship") or {}).get("state")=="PERSISTENT_FOREIGN_SELLING_PRICE_RESILIENCE",
        "foreign_buy_price_weakness":lambda i:(i.get("technical_relationship") or {}).get("state")=="FOREIGN_BUYING_PRICE_WEAKNESS",
        "flow_insufficient_history":lambda i:i["participant"]=="FOREIGN" and i["status"]=="INSUFFICIENT_HISTORY",
        "outside_foreign_cohort":lambda i:"OUTSIDE_RETAINED_FOREIGN_COHORT" in i["reason_codes"]}
    all_items=[(t,i) for t,r in sorted(artifact["records"].items()) for i in r["items"]]
    result={}
    for label,predicate in predicates.items():
        matches=[(t,i) for t,i in all_items if predicate(i)]
        result[label]={"selection":"FIRST_LEXICOGRAPHIC_TICKER_THEN_CONTRACT_ITEM_ORDER",
            "matching_evidence_items":len(matches),"status":"REAL_RETAINED_CASE" if matches else "NO_REAL_RETAINED_MATCH_SYNTHETIC_TESTS_ONLY",
            "ticker":matches[0][0] if matches else None,"evidence":matches[0][1] if matches else None}
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root",type=Path,required=True)
    parser.add_argument("--runtime-root",type=Path,required=True)
    parser.add_argument("--session",default="2026-10-02")
    parser.add_argument("--feature-batch",type=Path)
    parser.add_argument("--technical-acceptance",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--acceptance-output",type=Path,required=True)
    args=parser.parse_args(argv)
    destinations=[args.output.resolve(),args.acceptance_output.resolve()]
    for destination in destinations:
        if any(root.resolve() in destination.parents for root in (args.source_root/"operations-review",args.source_root/"config",args.source_root/"data",args.runtime_root)):
            raise ValueError("VOLUME_FLOW_OUTPUT_MUST_NOT_REPLACE_RETAINED_RUNTIME")
        if any(source and destination == source.resolve() for source in (args.feature_batch,args.technical_acceptance)):
            raise ValueError("VOLUME_FLOW_OUTPUT_MUST_NOT_REPLACE_SOURCE_INPUT")
    if len(set(destinations))!=2:raise ValueError("VOLUME_FLOW_OUTPUT_PATHS_MUST_DIFFER")
    baseline=json.loads(args.technical_acceptance.read_text(encoding="utf-8")) if args.technical_acceptance else None
    if args.feature_batch and (not baseline or baseline["session"]!=args.session):
        raise ValueError("TECHNICAL_BATCH_ACCEPTANCE_REQUIRED")
    start=time.perf_counter()
    with _offline_smoke_guard() as requests:
        artifact,inputs=collect(source_root=args.source_root,runtime_root=args.runtime_root,session=args.session,
            feature_batch=args.feature_batch,feature_batch_sha256=baseline["feature_batch_sha256"] if baseline else None)
        build_seconds=time.perf_counter()-start
        original=args.source_root/"operations-review/canonical-post-close-v1"/args.session/"enrichment/integrated_investment_decision_product.json"
        before=source_hash(original)
        if baseline and before!=baseline["source_hashes"]["decision"]:raise ValueError("RETAINED_DECISION_BYTES_DIFFER_FROM_TECHNICAL_ACCEPTANCE")
        digest=hashlib.sha256()
        postures=Counter()
        coherence_counts=Counter()
        coherence_changes=Counter()
        starting_coherence=starting_coherence_evaluator()
        references=context.research_references(artifact)
        def decision_record(ticker,row):
            if row["as_of_session"]!=args.session:raise ValueError("VOLUME_FLOW_DECISION_SESSION_INVALID")
            if decision.decision_identity(row)!=row["decision_identity"]:raise ValueError("VOLUME_FLOW_DECISION_IDENTITY_INVALID")
            digest.update(context.technical.market.canonical([ticker,row["decision_identity"],row["research_action_posture"],row.get("trigger"),row.get("invalidation"),row.get("portfolio_fit")]))
            postures[row["research_action_posture"]]+=1
            current_coherence=decision.evaluate_evidence_axis_coherence(row["evidence_axes"])
            old_coherence=starting_coherence(row["evidence_axes"])
            coherence_counts[current_coherence["state"]]+=1
            if current_coherence!=old_coherence:
                coherence_changes[old_coherence["state"]+"->"+current_coherence["state"]]+=1
            reference=references[ticker]
            assert reference["non_voting"] and reference["session"]==row["as_of_session"]
        meta,hash_value,count=stream_artifact(original,excluded=decision._IDENTITY_EXCLUDED,on_record=decision_record)
        assert hash_value==meta["artifact_sha256"] and count==artifact["universe_denominator"]
        assert source_hash(original)==before
        if baseline: assert digest.hexdigest()==baseline["before_after"]["comparison_digest"]
        assert all(not items for items in context.t0_projection(artifact).values())
        write_immutable(args.output,artifact)
        try:
            import psutil
            peak=getattr(psutil.Process().memory_info(),"peak_wset",None)
        except ImportError:peak=None
        report={"contract_version":"volume_and_flow_retained_acceptance/v1","context_contract":context.CONTRACT_VERSION,
            "starting_main":"20b168fe518ee58044010af0e812976ae5ea3ab9","session":args.session,
            "coverage":coverage(artifact),"foreign_retained_sessions":inputs.pop("foreign_sessions"),
            "source_bindings":inputs,"representative_cases":representative_cases(artifact),
            "aggregates":artifact["aggregates"],"artifact_identity":artifact["artifact_identity"],
            "artifact_sha256":source_hash(args.output),"non_regression":{"denominator":count,
                "decision_byte_sha256":before,"exact_decision_bytes_unchanged":True,"decision_identity_deltas":0,
                "posture_trigger_invalidation_policy_portfolio_deltas":0,"historical_t0_writes":0,
                "comparison_digest":digest.hexdigest(),"posture_counts":dict(sorted(postures.items())),
                "new_descriptive_coherence_state_counts":dict(sorted(coherence_counts.items())),
                "stage_0_descriptive_coherence_changes":dict(sorted(coherence_changes.items())),
                "contextual_technical_identity_deltas":0},
            "performance":{"context_build_seconds":round(build_seconds,6),"whole_acceptance_seconds":round(time.perf_counter()-start,6),
                "process_lifetime_peak_rss_bytes":peak,"context_artifact_bytes":args.output.stat().st_size,
                "input_bytes_parsed":inputs["input_bytes_parsed"],"decision_bytes_parsed":original.stat().st_size},
            "network_provider_calls":requests,"canonical_publication_writes":0,
            "historical_october_2_t0":"UNAVAILABLE_NO_RETROSPECTIVE_SEAL; ALL_REAL_ITEMS_POST_T0_ENRICHED",
            "authority_effect":context.AUTHORITY_EFFECT,"all_assertions_passed":True}
        args.acceptance_output.parent.mkdir(parents=True,exist_ok=True)
        args.acceptance_output.write_text(json.dumps(report,sort_keys=True,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"denominator":count,"coverage":report["coverage"],"performance":report["performance"]}),flush=True)


if __name__=="__main__": main()
