"""Offline retained-only qualification; no production Daily/acquisition/publication.

Rehydrates the already-built Producer operation, then executes the actual IID
identity / pre-seal Brief binding / build_delivery functions under a Job ceiling
and total deadline. Whole mode rebuilds IID from frozen products and exercises T0
and observers under scratch only; it never replaces historical production evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time


def child(args):
    sys.path.insert(0, str(args.code_root))
    import psutil
    from bounded_artifact_stream import stream_artifact, source_hash
    import daily_research_session_operations as operations
    import stocklookup_core.decision.integrated_investment_decision_product as iid
    from ai_research_session_delivery import build_delivery
    from feedback_resource_guard import memory_status
    code_paths = [Path(module.__file__) for module in (operations,iid)]
    code_paths += [args.code_root/name for name in ('bounded_artifact_stream.py',
        'ai_research_session_delivery.py','prospective_decision_retention.py','multi_session_signal_velocity.py',
        'canonical_post_close_pipeline.py','atomic_io.py')]
    code_paths += [Path(__file__).resolve(),Path(__file__).with_name('run_phase_c_whole_pipeline_rehearsal.py')]
    code_sha256 = {str(path):source_hash(path) for path in code_paths}

    process = psutil.Process()
    observations = []
    io_before = process.io_counters()._asdict()
    serialization_sizes = []
    original_canon = iid._canon
    def measured_canon(value):
        text = original_canon(value)
        serialization_sizes.append({'characters':len(text),'python_string_bytes':sys.getsizeof(text),
                                    'memory_at_return':process.memory_info()._asdict()})
        return text
    iid._canon = measured_canon
    started = time.perf_counter()
    def observe(stage):
        memory = process.memory_info()._asdict()
        observations.append(dict(stage=stage, elapsed=time.perf_counter()-started,
                                 memory=memory, system=memory_status()))
        (args.output/'progress.json').write_text(json.dumps(observations,indent=2)+'\n',encoding='utf-8')
    touched = {}
    def load(path):
        touched[str(path)] = source_hash(path)
        return json.loads(path.read_text(encoding="utf-8"))
    source = args.source_root
    session = args.session
    if args.stage in {'observer', 'consumers'}:
        from run_phase_c_whole_pipeline_rehearsal import observer, consumers
        observe('before_observer')
        proof = (observer(source, args.output, touched, observe) if args.stage == 'observer'
                 else consumers(source, args.output, touched, observe))
        unchanged = all(source_hash(Path(p)) == sha for p,sha in touched.items())
        assert unchanged
        args.result.write_text(json.dumps(dict(status='COMPLETED', elapsed=time.perf_counter()-started,
            observations=observations, proof=proof, protected_sources=touched,
            protected_sources_unchanged=unchanged), indent=2)+'\n',encoding='utf-8')
        return
    decision_path = source / 'operations-review/canonical-post-close-v1' / session / 'enrichment/integrated_investment_decision_product.json'
    records = {}
    touched[str(decision_path)] = source_hash(decision_path)
    metadata, digest, count = stream_artifact(decision_path,
        excluded={'artifact_identity', 'artifact_sha256', 'requested_at'},
        on_record=lambda t,r: records.update({t:r}) if args.stage not in {'whole','downstream'} else None)
    assert digest == metadata['artifact_sha256']
    construction_elapsed = None
    if args.stage in {'whole','downstream'}:
        from run_phase_c_whole_pipeline_rehearsal import rebuild_iid, load_daily_live_sources
        observe('before_iid_construction')
        live_sources = load_daily_live_sources(source,session,touched)
        observe('acquisition_and_enrichment_owners_live')
        decision, construction_elapsed = rebuild_iid(source, session, metadata, touched, observe,live_sources)
        records = decision['records']
    else:
        decision = dict(metadata, records=records)
    observe('resident_iid')
    t = time.perf_counter()
    identity = iid.content_identity(decision)
    identity_elapsed = time.perf_counter()-t
    assert identity['artifact_identity'] == metadata['artifact_identity']
    observe('identity')
    if args.stage == 'identity':
        result = dict(identity=identity, record_count=count, identity_elapsed=identity_elapsed)
    else:
        registry = load(source/'config/daily_research_session_input_registry.json')
        handoff = load(source/'operations-review/canonical-post-close-v1'/session/'session_handoff_bundle.json')
        op_identity = handoff['daily_session_operation_identity']
        directory = source/'operations-review/daily-research-session-operations-v1'/session/op_identity.split(':',1)[1]
        names = dict(peer='peer_relative_research_artifact.json', scenario='scenario_artifact.json',
            strategy='strategy_classification_artifact.json', product='current_daily_decision_research_product_artifact.json',
            snapshot='prospective_snapshot.json', corporate_snapshot='corporate_intelligence_prospective_context.json',
            strategy_snapshot='strategy_prospective_context.json', manifest='run_manifest.json',
            opportunity='opportunity_prioritization_artifact.json', decision_queue='daily_opportunity_decision_queue_artifact.json',
            opportunity_snapshot='opportunity_decision_prospective_context.json')
        operation = {k:load(directory/v) for k,v in names.items() if (directory/v).exists()}
        # Resolve the exact frozen selection without running any product builder.
        inputs, entries = operations.resolve_inputs(source, session, registry)
        for entry in entries.values():
            if isinstance(entry, dict) and entry.get('path'):
                path = source/entry['path']
                if path.is_file(): touched[str(path)] = source_hash(path)
        primary = load(directory/'ai_research_session_bundle.json')
        operation.update(inputs=inputs, portfolio_risk=None,
            source_freshness_matrix=primary.get('source_freshness_matrix'),
            macro_presentation_context=primary['market'].get('macro_presentation_context'),
            integrated_delivery=operations._integrated_delivery_binding(session=session,
                integrated_decision=decision,daily_integrated_brief=None,registry=registry))
        brief = load(directory/'daily_integrated_decision_brief_artifact.json')['daily_integrated_decision_brief']
        observe('before_binding')
        t = time.perf_counter()
        bound = operations.bind_integrated_decision_brief_before_sealing(operation,
            daily_integrated_decision_brief=brief,registry=registry)
        binding_elapsed = time.perf_counter()-t
        observe('after_binding')
        assert bound['manifest']['operation_identity'] == op_identity
        assert operation['integrated_delivery']['daily_integrated_decision_brief'] is None
        if args.stage in {'binding','downstream'}:
            result = dict(identity=identity,record_count=count,identity_elapsed=identity_elapsed,
                operation_identity=bound['manifest']['operation_identity'],binding_elapsed=binding_elapsed,
                borrowed_iid_records=bound['integrated_delivery']['integrated_investment_decision_product']['records'] is records)
            if args.stage == 'downstream':
                from run_phase_c_whole_pipeline_rehearsal import whole_tail
                result['downstream'] = whole_tail(source,args.output,session,decision,bound,handoff,touched,observe,
                                                live_sources,downstream_only=True)
        else:
            delivery_inputs = dict(bound['inputs'],integrated_investment_decision_product=
                bound['integrated_delivery']['integrated_investment_decision_product'],daily_integrated_decision_brief=brief)
            t = time.perf_counter()
            delivery = build_delivery(bound,delivery_inputs)
            delivery_elapsed = time.perf_counter()-t
            observe('delivery')
            filenames = dict(primary='ai_research_session_bundle.json',full_universe='ai_research_full_universe.ndjson',
                manifest='ai_research_bundle_manifest.json',brief='ai_research_session_brief.md',projection='current_decision_cockpit_projection.json')
            parity = {}
            written = 0
            for key,name in filenames.items():
                raw = delivery[key]
                expected = source_hash(directory/name)
                actual = hashlib.sha256(raw).hexdigest()
                parity[name] = dict(bytes=len(raw),actual_sha256=actual,retained_sha256=expected,equal=actual==expected)
                if args.write_outputs:
                    (args.output/name).write_bytes(raw)
                    written += len(raw)
            assert all(item['equal'] for item in parity.values()), 'RETAINED_DELIVERY_BYTE_PARITY_FAILED'
            result = dict(identity=identity,record_count=count,identity_elapsed=identity_elapsed,
                operation_identity=bound['manifest']['operation_identity'],binding_elapsed=binding_elapsed,
                delivery_elapsed=delivery_elapsed,output_parity=parity,bytes_written=written,
                borrowed_iid_records=bound['integrated_delivery']['integrated_investment_decision_product']['records'] is records)
            if args.stage == 'whole':
                del raw, delivery
                observe('delivery_last_reference_deleted')
                from run_phase_c_whole_pipeline_rehearsal import whole_tail
                result['whole'] = whole_tail(source, args.output, session, decision, bound, handoff,
                                             touched, observe,live_sources)
                del delivery_inputs, bound, operation, inputs, primary, decision, records,live_sources
                observe('analytical_references_deleted')
                import gc
                result['gc_collected'] = gc.collect()
                observe('after_gc')
                time.sleep(1)
                observe('idle_boundary')
    unchanged = all(source_hash(Path(p)) == sha for p,sha in touched.items())
    assert unchanged, 'PROTECTED_SOURCE_CHANGED'
    assert all(source_hash(Path(p)) == sha for p,sha in code_sha256.items()), 'REHEARSAL_CODE_CHANGED'
    result.update(status='COMPLETED',stage=args.stage,elapsed=time.perf_counter()-started,
        code_sha256=code_sha256,python=sys.version,
        observations=observations,construction_elapsed=construction_elapsed,serialization_sizes=serialization_sizes,process_io_before=io_before,process_io_after=process.io_counters()._asdict(),protected_sources=touched,protected_sources_unchanged=unchanged,
        input_unique_bytes=sum(Path(p).stat().st_size for p in touched),
        byte_accounting='Unique source sizes; hashing/proof rereads additional bytes. OS cache/physical IO unmeasured.',
        authority_effect='NONE / RESOURCE_AND_RUNTIME_SIMPLIFICATION_ONLY')
    args.result.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-root','code-root','output','result'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--session',default='2026-10-06')
    parser.add_argument('--stage',choices=('identity','binding','producer','whole','observer','consumers','downstream'),default='producer')
    parser.add_argument('--deadline',type=float,default=1200)
    parser.add_argument('--memory-gib',type=float,default=7)
    parser.add_argument('--child',action='store_true')
    parser.add_argument('--write-outputs',action='store_true')
    args = parser.parse_args()
    for name in ('source_root','code_root','output','result'):
        setattr(args,name,getattr(args,name).resolve())
    if any(path == args.source_root or args.source_root in path.parents for path in (args.output,args.result)):
        parser.error('Output and result must be outside retained source root')
    args.output.mkdir(parents=True,exist_ok=True)
    if args.child:
        child(args)
        return
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from feedback_resource_guard import ResourcePolicy, run_bounded
    command = [sys.executable,'-B',str(Path(__file__).resolve()),*sys.argv[1:],'--child']
    policy = ResourcePolicy(args.deadline,int(args.memory_gib*1024**3),0,0,0)
    result = run_bounded(command,cwd=args.code_root,policy=policy,result_path=args.result,
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    (args.output/'containment.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result.get(k) for k in ('outcome','reason_code','wall_seconds','containment','reaped','peak_process_bytes')}))
    if result.get('outcome') != 'COMPLETED' or not result.get('reaped') or result.get('reason_code'):
        # The guard's operational status is authoritative; a failed rehearsal is
        # not a proof even if a partial child diagnostic exists.
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
