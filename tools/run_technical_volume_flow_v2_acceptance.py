"""Single bounded, retained-only paired semantic migration acceptance.

Explicit roots; one price pass; indexed V1 batch; no Daily, acquisition or T0 write.
New outputs describe October 2 as REPLAY_DIAGNOSTIC / NON_AUTHORITATIVE.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import canonical_market_bars as bars
import contextual_technical_features as old_technical
import contextual_technical_features_v2 as technical
import contextual_technical_dispatch as dispatch
import technical_relationship_view as bridge
import volume_and_flow_context as old_flow
import volume_and_flow_context_v2 as flow
import volume_and_flow_retained as retained
import daily_session_level2_package as level2
import market_wide_historical_research_context as history
import stocklookup_core.decision.integrated_investment_decision_product as decision
import prospective_decision_retention as retention
import prospective_pit_capture_retention as capture_store
from bounded_artifact_stream import header, source_hash, stream_artifact
from daily_session_completion_reference import load_qualified_completed_sessions
from tools.run_volume_and_flow_context import coverage as flow_coverage
from tools.run_prospective_pit_capture_acceptance import _receipt_inventory
from test_production_call_shape_smoke import _offline_smoke_guard

START = "bb3dea293ce9c7f757d3bd9e6f1f9fb22af82517"
AUTHORITY = "NONE / DESCRIPTIVE_SEMANTIC_VERSION_MIGRATION_ONLY"
PIT_MODULES = ("prospective_pit_capture.py", "prospective_pit_capture_retention.py", "governed_session_chain.py",
    "prospective_market_evidence_retention.py", "raw_pit_authority_matrix.py", "multi_source_exact_session_resolver.py",
    "daily_producer_pipeline.py", "canonical_daily_operation.py")


def memory():
    import psutil
    info=psutil.Process().memory_info()
    return {"rss_bytes":info.rss,"process_lifetime_peak_rss_bytes":getattr(info,"peak_wset",info.rss)}


def counts(values): return dict(sorted(Counter(values).items()))


def audit_outputs(technical_path, view_path, flow_path):
    """Reopen only newly produced batches under the final public verifiers."""
    contexts, expected_views = {}, {}
    with Path(technical_path).open(encoding="utf-8") as source:
        for line in source:
            row=json.loads(line);c=row["contextual_technical"]
            dispatch.verify_context(c,ticker=row["ticker"],session=c["as_of_session"])
            contexts[row["ticker"]]=c["artifact_identity"]
            expected_views[row["ticker"]]={tf:v["view_identity"] for tf,v in bridge.build_views(c).items()}
    view_count=0
    with Path(view_path).open(encoding="utf-8") as source:
        for line in source:
            row=json.loads(line)
            for tf,v in row["relationship_views"].items():
                bridge.verify_view(v)
                assert v["source"]["context_identity"]==contexts[row["ticker"]]
                assert v["view_identity"]==expected_views[row["ticker"]][tf]
                view_count+=1
    def record(t,row):
        flow.verify(row,"volume_flow_instrument/v2")
        for item in row["items"]:
            flow.verify(item,flow.ITEM_VERSION)
            assert item["knowledge_stage"]==flow.POST and item["non_voting"] is True and item["is_actionable"] is False
            if item["domain"]=="VOLUME":
                relation=item["technical_participation_relationship"]
                assert relation["view_identity"]==expected_views[t][item["horizon"].split("/")[0]]
                bridge.checked(item["participation_measure"],flow.PARTICIPATION_MEASURES,"participation_measure")
                bridge.checked(item["participation_state"],flow.PARTICIPATION_MEASURES[item["participation_measure"]],"participation_state")
    meta,digest,record_count=stream_artifact(Path(flow_path),excluded={"artifact_identity","artifact_sha256"},on_record=record)
    assert digest==meta["artifact_sha256"] and meta["contract_version"]==flow.CONTRACT_VERSION
    return {"technical_contexts":len(contexts),"relationship_views":view_count,"volume_flow_records":record_count,"status":"PASS"}


def observation(old, new, tf):
    a,b=old["timeframes"][tf],new["timeframes"][tf]
    before=a["features"]["structure"].get("values") or {}
    after=b["features"]["structure"].get("values") or {}
    setup=b["features"]["setup_state"].get("values") or b["features"]["setup_state"]["diagnostics"]
    return {"owner_market_structure_state":before.get("swing_structure",{}).get("market_structure_state","UNAVAILABLE"),
        "old_repair_context":(a["features"]["interpretation"].get("values") or {}).get("repair_context","UNAVAILABLE"),
        "old_direction":before.get("direction","UNAVAILABLE"),
        "swing_high_relation":after.get("swing_high_relation","UNKNOWN"),"swing_low_relation":after.get("swing_low_relation","UNKNOWN"),
        "swing_relation":after.get("swing_relation","UNKNOWN"),"retained_swing_prices":after.get("retained_swing_prices"),
        "trend_reading":after.get("trend_reading","UNKNOWN"),"setup_state":setup["state"],"setup_rule":setup["rule"],
        "setup_reasons":setup["reason_codes"],"primitive_availability":setup["primitive_availability"],"setup_conflicts":setup["setup_conflicts"],
        "range_state":(b["features"]["range_consolidation"].get("values") or {}).get("state","UNKNOWN"),
        "temporal":b["context"]["temporal"],"bos":after.get("bos"),"choch":after.get("choch"),"breakout_event":after.get("breakout_event")}


def summarize(old, new):
    result={}
    for tf in technical.TIMEFRAMES:
        rows=[observation(old[t],new[t],tf) for t in sorted(new)]
        formerly_non_bearish=[r for r in rows if r["setup_state"] in {"BEARISH_STRUCTURE_BREAK","FAILED_BREAKOUT_DETERIORATION","CONTINUING_DETERIORATION"}
            and r["old_repair_context"] not in {"CONTINUING_DETERIORATION","DETERIORATION_AFTER_EXTENSION","UNAVAILABLE"}]
        old_unknown_sideways=[r for r in rows if r["old_repair_context"]=="SIDEWAYS_RANGE" and r["old_direction"]=="UNKNOWN"]
        assert not any(r["setup_state"]=="SIDEWAYS" for r in old_unknown_sideways)
        result[tf]={"scope":len(rows), **{key:counts(r[key] for r in rows) for key in
            ("swing_high_relation","swing_low_relation","swing_relation","trend_reading","setup_state","setup_rule","range_state")},
            "any_exact_swing_tie":sum("EQUAL" in (r["swing_high_relation"],r["swing_low_relation"]) for r in rows),
            "owner_vs_descriptive_swing":counts(r["owner_market_structure_state"]+" -> "+r["swing_relation"] for r in rows),
            "old_repair_to_new_setup":counts(r["old_repair_context"]+" -> "+r["setup_state"] for r in rows),
            "bearish_cases_previously_non_bearish":len(formerly_non_bearish),
            "unknown_to_sideways_eliminated":len(old_unknown_sideways),
            "temporal_states":counts(r["temporal"]["state"] for r in rows),
            "periods_behind":counts(str(r["temporal"]["periods_behind"]) for r in rows),
            "later_period_completeness_states":counts(r["temporal"]["later_period_completeness"]["state"] for r in rows),
            "later_period_completeness_totals":dict(sorted(sum((Counter(r["temporal"]["later_period_completeness"]["counts"] or {}) for r in rows),Counter()).items())),
            "primitive_availability":{name:counts(r["primitive_availability"][name] for r in rows) for name in rows[0]["primitive_availability"]},
            "setup_conflicts":counts(code for r in rows for code in r["setup_conflicts"]),
            "reason_codes":counts(code for r in rows for code in r["setup_reasons"])}
    result["multi_timeframe"]={"states":counts(c["multi_timeframe"]["state"] for c in new.values()),
        "eligible_counts":counts(str(c["multi_timeframe"]["eligible_count"]) for c in new.values()),
        "old_to_new":counts(old[t]["multi_timeframe"]["state"]+" -> "+new[t]["multi_timeframe"]["state"] for t in new)}
    return result


def verify_old_t0(root, baseline):
    paths=sorted((root/"operations-review/prospective-decision-retention-v1").glob("*/*/prospective_decision_snapshot.json"))
    before={p.relative_to(root).as_posix():source_hash(p) for p in paths}
    if before != baseline["historical_t0"]["source_hashes"]: raise ValueError("T0_BASELINE_BYTES_CHANGED")
    verified, empty, decisions, technical_versions = 0,0,0,Counter()
    for path in paths:
        if path.stat().st_size==0:
            empty+=1
            continue
        def record(t,row):
            body={k:v for k,v in row.items() if k!="prospective_snapshot_record_identity"}
            assert row["prospective_snapshot_record_identity"]==retention.RECORD_PREFIX+retention._hash(body)
            c=((row.get("integrated_decision_at_t0") or {}).get("contextual_technical_context") or {}).get("projection")
            if c: technical_versions[dispatch.verify_context(c,ticker=t,session=row["decision_session"])]+=1
        meta,digest,count=stream_artifact(path,excluded={"snapshot_identity"},on_record=record)
        assert meta["snapshot_identity"]==retention.SNAPSHOT_PREFIX+digest and meta["contract_version"]==retention.CONTRACT_VERSION
        verified+=1;decisions+=count
        print("OLD_T0_VERIFIED",verified,flush=True)
    return paths,before,{"files":len(paths),"valid_snapshots_verified":verified,"original_empty_october_2_file":empty,
        "records_verified":decisions,"retained_technical_versions":dict(technical_versions),"writes":0,
        "historical_october_2":"UNAVAILABLE_NO_RETROSPECTIVE_SEAL"}


def run(args):
    root,runtime=Path(args.source_root),Path(args.runtime_root)
    session=args.session
    if session!="2026-10-02": raise ValueError("MIGRATION_ACCEPTANCE_REQUIRES_RETAINED_OCTOBER_2")
    destinations=[Path(args.output),Path(args.technical_output),Path(args.view_output),Path(args.flow_output)]
    protected_roots=(root/"operations-review",root/"config",root/"data",runtime)
    for output in destinations:
        if any(output.resolve().is_relative_to(p.resolve()) for p in protected_roots): raise ValueError("ACCEPTANCE_OUTPUT_MUST_BE_SEPARATE")
    if len({p.resolve() for p in destinations})!=len(destinations): raise ValueError("ACCEPTANCE_OUTPUT_PATHS_MUST_DIFFER")
    paths=level2.session_artifact_paths(root,session)
    paths={k:paths[k] for k in ("exact_session_snapshot","universe_resolution","technical_recovery")}
    paths.update(input_registry=root/"config/daily_research_session_input_registry.json",calendar=root/"config/governed_trading_session_calendar_v1.json",
        decision=root/"operations-review/canonical-post-close-v1"/session/"enrichment/integrated_investment_decision_product.json",
        current_research=root/"operations-review/canonical-post-close-v1"/session/"enrichment/historical_context.json",
        v1_technical=Path(args.v1_technical),v1_flow=Path(args.v1_flow))
    registry=json.loads(paths["input_registry"].read_bytes());binding=registry["sessions"][session]
    paths.update(events=root/binding["event_context"]["path"],descriptive=root/binding["descriptive"]["path"])
    paths.update({"foreign_"+p.stem:p for p in retained.store.observations_root(runtime).glob("*.json")})
    if (runtime/"vn_stock.db").exists():paths["date_ledger"]=runtime/"vn_stock.db"
    baseline=json.loads((ROOT/"docs/internal/PROSPECTIVE_PIT_CAPTURE_COMPLETENESS_ACCEPTANCE.json").read_bytes())
    before={k:source_hash(p) for k,p in paths.items()}
    for name,key in (("IntegratedDecision","decision"),("CurrentResearch","current_research"),("TechnicalContext","v1_technical"),("VolumeFlowContext","v1_flow")):
        assert before[key]==baseline["protected_product_bytes"][name]["sha256"]
    for output in destinations:
        if output.resolve() in {p.resolve() for p in paths.values()}: raise ValueError("OUTPUT_REPLACES_INPUT")
    modules={p:source_hash(ROOT/p) for p in PIT_MODULES}
    assert modules=={p:source_hash(root/p) for p in PIT_MODULES}
    calendar_paths=sorted((Path(args.calendar_root)/"operations-review/prospective-calendar-evidence-v1").rglob("*.json"))
    calendar_receipts=capture_store.load_calendars(args.calendar_root)
    calendar_paths += [Path(args.calendar_root)/"operations-review/prospective-calendar-evidence-v1/raw"/row["payload_sha256"] for row in calendar_receipts]
    calendar_hashes={p.as_posix():source_hash(p) for p in calendar_paths}
    assert calendar_paths
    started=time.perf_counter();timings={}
    with _offline_smoke_guard() as requests:
        old={}
        with paths["v1_technical"].open(encoding="utf-8") as source:
            for line in source:
                row=json.loads(line);ticker=row["ticker"]
                if ticker in old: raise ValueError("TECHNICAL_BATCH_DUPLICATE_TICKER")
                c=row["contextual_technical"];dispatch.verify_context(c,ticker=ticker,session=session);old[ticker]=c
        old_foreign={}
        def old_flow_record(t,row):
            old_flow.verify(row,"volume_flow_instrument/v1")
            for item in row["items"]:old_flow.verify(item,old_flow.ITEM_VERSION)
            old_foreign[t]=[{k:i[k] for k in ("values","status","reason_codes","coverage_scope","unit_semantics","session_continuity")}
                for i in row["items"] if i["participant"]=="FOREIGN"]
        old_meta,old_digest,old_count=stream_artifact(paths["v1_flow"],excluded={"artifact_identity","artifact_sha256"},on_record=old_flow_record)
        assert old_digest==old_meta["artifact_sha256"] and old_meta["contract_version"]==old_flow.CONTRACT_VERSION
        timings["v1_verification"]={"seconds":round(time.perf_counter()-started,6),**memory()}
        universe=json.loads(paths["universe_resolution"].read_bytes());history._verify_hashed_identity(universe,label="V2_UNIVERSE")
        recovery=json.loads(paths["technical_recovery"].read_bytes());history._verify_hashed_identity(recovery,label="V2_RECOVERY")
        source=header(paths["exact_session_snapshot"]);cutoff=source["requested_at"]
        assert source["resolved_completed_session"]==session and recovery["source_lineage"]["p3f9b_snapshot_identity"]==source["snapshot_identity"]
        scope={t for t,r in universe["records"].items() if r["activity_and_session_state"] in history.IN_SCOPE_ACTIVITY_STATES}
        assert set(old)==scope
        calendar=bars.governed_calendar_projection(json.loads(paths["calendar"].read_bytes()))
        event=json.loads(paths["events"].read_bytes());import current_official_event_context as events_module
        assert all(event.get(k)==v for k,v in events_module._identity(event).items()) and event["artifact_identity"]==binding["event_context"]["artifact_identity"]
        events=defaultdict(list)
        for row in event["records"].values():
            for e in row.get("events",[]):events[e["ticker"]].append(e)
        dates=retained.trading_date_index(runtime);registry_dates=load_qualified_completed_sessions(paths["input_registry"])
        foreign=retained.flow_index(runtime,session,dates,registry_dates)
        records,views,prepared,all_tickers={},{},{},set()
        compat=Counter();build_seconds=Counter();stage_memory={};owner_deltas=0;v1_rebuild_deltas=0
        for output in destinations[1:]:output.parent.mkdir(parents=True,exist_ok=True)
        with Path(args.technical_output).open("wb") as tech_out,Path(args.view_output).open("wb") as view_out:
            def price_record(ticker,row):
                nonlocal owner_deltas,v1_rebuild_deltas
                all_tickers.add(ticker)
                if ticker not in scope:return
                override=recovery.get("recovered_history_overrides",{}).get(ticker,{})
                recovered=override.get("state")=="RECOVERED_COMPLETE_TECHNICAL_HISTORY"
                observations=override.get("observations",[]) if recovered else row.get("observations",[])
                moment=time.perf_counter()
                series=bars.research_series(observations,ticker=ticker,target_session=session,knowledge_cutoff=cutoff,
                    source_identity=recovery["artifact_identity"] if recovered else source["snapshot_identity"],calendar_evidence=calendar,ca_events=events[ticker])
                build_seconds["canonical_foundation"]+=time.perf_counter()-moment
                moment=time.perf_counter()
                rebuilt=old_technical.build_context(series,ticker=ticker,as_of_session=session,knowledge_cutoff=cutoff)
                v1_rebuild_deltas+=rebuilt!=old[ticker]
                assert rebuilt==old[ticker], "V1_REBUILD_DELTA:"+ticker
                build_seconds["v1_rebuild_freeze"]+=time.perf_counter()-moment
                moment=time.perf_counter()
                c=technical.build_context(series,ticker=ticker,as_of_session=session,knowledge_cutoff=cutoff)
                technical.verify_context(c,ticker,session)
                records[ticker]={"multi_timeframe":bars.project_research_series(series,target_session=session,knowledge_cutoff=cutoff),"contextual_technical":c}
                build_seconds["technical_v2"]+=time.perf_counter()-moment;stage_memory["technical_v2"]=memory()
                for tf in technical.TIMEFRAMES:
                    a=old[ticker]["timeframes"][tf]["features"]["structure"].get("values") or {}
                    b=c["timeframes"][tf]["features"]["structure"].get("values") or {}
                    owner_deltas+=any(a.get(k)!=b.get(k) for k in ("bos","choch","breakout","breakout_event","swing_sequence"))
                    if a:owner_deltas+=a["swing_structure"]["market_structure_state"]!=b["tactical_owner_market_structure_state"]
                moment=time.perf_counter();views[ticker]=bridge.build_views(c)
                build_seconds["relationship_view"]+=time.perf_counter()-moment;stage_memory["relationship_view"]=memory()
                moment=time.perf_counter()
                prepared[ticker]=flow.volume_items(views[ticker],series=series,exhaustive_dates=dates.get(ticker,()),registry_dates=registry_dates)
                build_seconds["volume_flow_v2"]+=time.perf_counter()-moment;stage_memory["volume_flow_v2"]=memory()
                moment=time.perf_counter()
                legacy_views=bridge.build_views(old[ticker])
                legacy_items=flow.volume_items(legacy_views,series=series,exhaustive_dates=dates.get(ticker,()),registry_dates=registry_dates)
                compat.update(i["knowledge_stage"] for i in legacy_items)
                assert all(i["knowledge_stage"]==flow.POST for i in legacy_items)
                build_seconds["explicit_v1_to_v2_compatibility"]+=time.perf_counter()-moment
                for chunk in retention._json_bytes({"ticker":ticker,**records[ticker]}):tech_out.write(chunk)
                tech_out.write(b"\n")
                for chunk in retention._json_bytes({"ticker":ticker,"relationship_views":views[ticker]}):view_out.write(chunk)
                view_out.write(b"\n")
                if len(records)%100==0:print("PAIRED_V2",len(records),flush=True)
            price_meta,price_digest,price_count=stream_artifact(paths["exact_session_snapshot"],excluded={"snapshot_identity","snapshot_sha256"},on_record=price_record,sanitize=True)
        assert price_digest==source["snapshot_sha256"] and all_tickers==set(universe["records"])
        assert v1_rebuild_deltas==owner_deltas==0 and len(records)==1503 and price_count==1683
        sectors={}
        def sector_record(t,r):
            import current_market_sector_leadership_context as leadership
            key=leadership._classification_key(r)
            if key is not None:sectors[t]="|".join(key)
        sector_meta,sector_digest,_=stream_artifact(paths["descriptive"],excluded={"artifact_identity","artifact_sha256"},on_record=sector_record)
        assert sector_digest==sector_meta["artifact_sha256"] and sector_meta["artifact_identity"]==binding["descriptive"]["artifact_identity"]
        moment=time.perf_counter()
        artifact=flow.build_artifact(session=session,tickers=all_tickers,relationship_views=views,flow_series=foreign,
            exhaustive_dates=dates,registry_dates=registry_dates,sectors=sectors,prepared_volume_items=prepared,
            source_artifact_identities=[source["snapshot_identity"],recovery["artifact_identity"],universe["artifact_identity"],event["artifact_identity"],sector_meta["artifact_identity"]])
        build_seconds["volume_flow_v2"]+=time.perf_counter()-moment;stage_memory["volume_flow_v2"]=memory()
        for t,row in artifact["records"].items():
            actual=[{k:i[k] for k in ("values","status","reason_codes","coverage_scope","unit_semantics","session_continuity")} for i in row["items"] if i["participant"]=="FOREIGN"]
            assert actual==old_foreign[t]
        assert all(not items for items in flow.t0_projection(artifact).values())
        parent={"contract_version":history.CONTRACT_VERSION,"session":session,"records":records};parent.update(history.content_identity(parent))
        verified_bars=decision.market_bar_context_records(parent,session=session,requested_at=cutoff)
        verified=dispatch.verified_context_records(parent,session=session,knowledge_cutoff=cutoff,verified_bar_contexts=verified_bars)
        assert all(v["status"]=="AVAILABLE" for v in verified.values())
        comparison=hashlib.sha256();postures=Counter();record_deltas=0
        def decision_record(t,row):
            nonlocal record_deltas
            before_row=copy.deepcopy(row);original_identity=decision.decision_identity(row)
            assert original_identity==row["decision_identity"] and row["as_of_session"]==session
            if t in verified:decision.attach_contextual_technical(row,verified[t])
            assert decision.decision_identity(row)==original_identity
            # Exact record comparison permits only the two authorized explanatory fields.
            for candidate in (row,before_row):
                candidate.pop("contextual_technical_context",None)
                candidate["evidence_axes"]["TACTICAL_STRUCTURE"].pop("contextual_feature_reference",None)
            record_deltas+=row!=before_row
            postures[row["research_action_posture"]]+=1
            comparison.update(technical.market.canonical([t,original_identity,row["research_action_posture"],row.get("trigger"),row.get("invalidation"),row.get("portfolio_fit")]))
        decision_meta,decision_digest,decision_count=stream_artifact(paths["decision"],excluded=decision._IDENTITY_EXCLUDED,on_record=decision_record)
        assert decision_digest==decision_meta["artifact_sha256"] and decision_count==1683 and record_deltas==0
        print("DECISION_PARITY",decision_count,flush=True)
        t0_paths,t0_hashes,t0_result=verify_old_t0(root,baseline)
        receipt_paths,receipt_counts,receipt_digest=_receipt_inventory(root)
        assert receipt_digest==baseline["old_immutable_receipts"]["before_after_digest"] and len(receipt_paths)==908
        readiness=capture_store.CaptureIndex(root,cutoff="2026-10-03T23:59:59Z").readiness(session=session)
        assert readiness["status"]=="NOT_CAPTURED" and readiness["first_complete_capture_session"] is None
        assert readiness["complete_session_count"]==0 and not any(readiness["counts_at_depth"].values()) and readiness["evaluation_authorized"] is False
        with Path(args.flow_output).open("wb") as output:
            for chunk in retention._json_bytes(artifact,pretty=True):output.write(chunk)
        moment=time.perf_counter()
        final_audit=audit_outputs(args.technical_output,args.view_output,args.flow_output)
        build_seconds["final_batch_verification"]+=time.perf_counter()-moment
        assert before=={k:source_hash(p) for k,p in paths.items()}
        assert t0_hashes=={p.relative_to(root).as_posix():source_hash(p) for p in t0_paths}
        assert calendar_hashes=={p.as_posix():source_hash(p) for p in calendar_paths}
        assert modules=={p:source_hash(ROOT/p) for p in PIT_MODULES}
        _,after_counts,after_receipt_digest=_receipt_inventory(root)
        assert receipt_counts==after_counts and receipt_digest==after_receipt_digest
        assert requests=={"network":0,"provider":0,"vnstock_import":0}
        new={t:r["contextual_technical"] for t,r in records.items()}
        items=[i for r in artifact["records"].values() for i in r["items"]]
        names=[t if t in new else sorted(new)[n] for n,t in enumerate(("AAA","ABI","AAM","A32","ANI","AAN"))]
        report={"contract_version":"paired_technical_volume_flow_semantic_migration_acceptance/v1","starting_main":START,"session":session,
            "evaluation_scope":"REPLAY_DIAGNOSTIC","authority_status":"NON_AUTHORITATIVE","authority_effect":AUTHORITY,
            "universe_denominator":1683,"technical_scope":1503,"technical_v2_distributions":summarize(old,new),
            "feature_coverage":technical.coverage(records),"volume_flow_v2_coverage":flow_coverage(artifact),
            "relationship_view_coverage":{tf:counts(v[tf]["availability"]["structure_status"] for v in views.values()) for tf in technical.TIMEFRAMES},
            "typed_participation_measures":counts(i["participation_measure"] or "NOT_APPLICABLE_PARTICIPANT_VALUE" for i in items),
            "participation_states_by_measure":{m:counts(i["participation_state"] for i in items if i["participation_measure"]==m) for m in flow.PARTICIPATION_MEASURES},
            "aggregates":artifact["aggregates"],"foreign_sessions":{t:[o["session_date"] for o in s["observations"]] for t,s in foreign.items()},
            "representative_cases":{t:{"selection":"REQUESTED_TICKER_OR_DETERMINISTIC_LEXICOGRAPHIC_SUBSTITUTE","timeframes":{tf:observation(old[t],new[t],tf) for tf in technical.TIMEFRAMES},
                "multi_timeframe":new[t]["multi_timeframe"],"participation":[{k:i[k] for k in ("horizon","status","participation_measure","participation_state","knowledge_stage","reason_codes")} for i in artifact["records"][t]["items"]]} for t in names},
            "v1_freeze":{"technical_contexts_verified":len(old),"rebuilt_v1_record_deltas":v1_rebuild_deltas,"volume_flow_records_verified":old_count,
                "foreign_value_semantic_deltas":0,"tactical_owner_field_deltas":owner_deltas,"old_t0":t0_result},
            "explicit_v1_to_v2_compatibility":{"scope":1503,"volume_evidence_items":sum(compat.values()),"knowledge_stage_counts":dict(compat),"legacy_repair_labels_consumed":False},
            "non_regression":{"decisions":decision_count,"exact_all_other_decision_field_deltas":record_deltas,"decision_identity_deltas":0,
                "policy_posture_phase_trigger_invalidation_portfolio_owner_field_deltas":0,"posture_counts":dict(sorted(postures.items())),"comparison_digest":comparison.hexdigest(),
                "protected_original_bytes_unchanged":True,"technical_v2_product_adapters_verified":len(verified)},
            "pit_compatibility":{"modules_sha256":modules,"old_receipts":len(receipt_paths),"old_receipt_classification":receipt_counts,"receipt_digest":receipt_digest,
                "old_calendar_sha256":calendar_hashes,"old_t0_sha256":t0_hashes,"readiness":{k:readiness[k] for k in ("status","first_complete_capture_session","complete_session_count","counts_at_depth","evaluation_authorized")}},
            "first_real_post_release_capture_acceptance":{"status":"PENDING","additional_requirements":["EXACT_GENUINE_TECHNICAL_V2_T0_IDENTITY","NORMAL_V2_VOLUME_FLOW_ROUTING","NO_POST_T0_EVIDENCE_IN_T0_PROJECTION"],"live_daily_run":False},
            "final_public_verifiers":final_audit,
            "source_hashes":before,"output_artifacts":{p.name:{"bytes":p.stat().st_size,"sha256":source_hash(p)} for p in destinations[1:]},
            "performance":{"stage_seconds":{k:round(v,6) for k,v in build_seconds.items()},"stage_memory":stage_memory,"v1_verification":timings["v1_verification"],
                "whole_acceptance_seconds":round(time.perf_counter()-started,6),**memory(),"price_corpora_parsed":1,"v1_technical_batches_parsed":1,"v1_volume_flow_corpora_parsed":1,
                "decision_corpora_parsed":1,"json_member_limit_bytes":16*1024*1024,"canonical_series_peak_scope":"ONE_INSTRUMENT","per_ticker_relationship_files":0},
            "network_provider_calls":requests,"historical_t0_writes":0,"canonical_publication_writes":0,"next_gate":"THESIS_EVIDENCE_MATRIX_AND_CONFLICT_ENGINE_V1_STAGE_1",
            "next_gate_started":False,"all_assertions_passed":True}
        report.update(market_identity(report))
        Path(args.output).parent.mkdir(parents=True,exist_ok=True)
        Path(args.output).write_text(json.dumps(report,sort_keys=True,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"denominator":1683,"scope":1503,"performance":report["performance"],"all_assertions_passed":True}),flush=True)
    return report


def market_identity(value):return technical.identity(value,kind="paired_technical_volume_flow_semantic_migration_acceptance")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("source-root","runtime-root","calendar-root","v1-technical","v1-flow","output","technical-output","view-output","flow-output"):
        parser.add_argument("--"+name,type=Path,required=True)
    parser.add_argument("--session",default="2026-10-02")
    run(parser.parse_args())


if __name__=="__main__":main()
