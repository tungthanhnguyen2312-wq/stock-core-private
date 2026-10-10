"""Scratch-only heavy-path tail used by the contained Phase C rehearsal.

Reconstructs the retained live set, exercises actual T0/hash/write/index functions
against scratch, then the production retained observer. No production orchestrator,
provider, capture/marker builder or runtime DB is called.
"""
import gc
import json
import time
from pathlib import Path


def load_daily_live_sources(source, session, touched):
    import daily_session_level2_package as level2
    from bounded_artifact_stream import source_hash
    paths = level2.session_artifact_paths(source,session)
    selected = {'exact':paths['exact_session_snapshot']}
    folder = source/'operations-review/canonical-post-close-v1'/session/'enrichment'
    selected.update({name:folder/(name+'.json') for name in ('historical_context','financial_momentum','corporate_event_context')})
    result={}
    for name,path in selected.items():
        touched[str(path)]=source_hash(path)
        result[name]=json.loads(path.read_text(encoding='utf-8'))
    return result


def rebuild_iid(source, session, metadata, touched, observe, live_sources):
    """Actual IID builder over its frozen, already-materialized upstream products."""
    import daily_session_level2_package as level2
    import integrated_investment_decision_product as iid
    from bounded_artifact_stream import source_hash
    paths = level2.session_artifact_paths(source, session)
    def load(path):
        if not path.is_file(): return None
        touched[str(path)] = source_hash(path)
        return json.loads(path.read_text(encoding='utf-8'))
    mapping = dict(technical_structure_artifact='market_structure_breakout_v3_projection',
        current_valuation_artifact='current_valuation_evaluated', relative_volume_artifact='liquidity_research',
        market_sector_artifact='sector_leadership',legacy_decision_artifact='opportunity_prioritization',
        technical_coverage_disposition_artifact='technical_coverage_disposition',momentum_artifact='tactical_momentum_context',
        tactical_confirmation_artifact='tactical_confirmation_context',tactical_boundaries_artifact='tactical_confirmation_invalidation_boundaries',
        operational_fundamental_integration_artifact='operational_fundamental_context_integration',
        liquidity_research_artifact='liquidity_research', official_liquidity_artifact='official_liquidity',
        entity_applicability_artifact='current_research_entity_applicability')
    kwargs = {arg:load(paths[key]) for arg,key in mapping.items()}
    # Relative volume is an on-demand context, not the descriptive liquidity artifact.
    import market_wide_relative_volume_research as rvol
    exact = load(paths['exact_session_snapshot'])
    requested = f'{session}T15:00:00+07:00'
    kwargs['relative_volume_artifact'] = rvol.build_artifact(candidates=sorted(exact['records']),
        records=exact['records'],session=session,requested_at=requested)
    financial = load(paths['financial_analysis_product'])
    kwargs['financial_analysis_artifact'] = financial['financial_analysis_product']
    kwargs['financial_peer_materialization_artifact'] = financial
    kwargs['historical_context_artifact'] = live_sources['historical_context']
    kwargs['corporate_intelligence_artifact'] = load(source/'operations-review/canonical-post-close-v1'/session/'enrichment/corporate_intelligence_axis.json')
    from canonical_post_close_pipeline import resolve_current_session_priority_queue
    kwargs['priority_queue_artifact'], _ = resolve_current_session_priority_queue(session,
        opportunity=kwargs['legacy_decision_artifact'],triage=load(paths['session_triage']))
    observe('frozen_iid_builder_inputs')
    t = time.perf_counter()
    decision = iid.build_artifact(session=session,requested_at=metadata['requested_at'],**kwargs)
    observe('iid_constructed')
    assert decision['artifact_identity'] == metadata['artifact_identity'], 'REBUILT_IID_IDENTITY_MISMATCH'
    elapsed = time.perf_counter()-t
    del kwargs, exact, financial
    observe('iid_upstream_locals_deleted')
    return decision, elapsed


def observer(source, output, touched, observe):
    from bounded_artifact_stream import source_hash
    import multi_session_signal_velocity as velocity
    # Guard every exact source actually read by the discovery loader/projection.
    original_load = velocity._load
    def protected_load(path):
        if path.is_file(): touched[str(path)] = source_hash(path)
        return original_load(path)
    velocity._load = protected_load
    original_project = getattr(velocity, '_project_snapshot', None)
    if original_project:
        def protected_project(path):
            if path.is_file(): touched[str(path)] = source_hash(path)
            return original_project(path)
        velocity._project_snapshot = protected_project
    t = time.perf_counter()
    try:
        artifact = velocity.build_from_retained_root(source)
    finally:
        velocity._load = original_load
        if original_project: velocity._project_snapshot = original_project
    observe('signal_velocity_built')
    retained = source/'operations-review/multi-session-signal-velocity-v1.2/2026-10-06/multi_session_signal_velocity_artifact.json'
    touched[str(retained)] = source_hash(retained)
    # Hash the retained output record-wise without keeping a second result graph.
    from bounded_artifact_stream import ObjectStream, canonical_bytes
    import hashlib
    digest = hashlib.sha256(); digest.update(b'{'); first = True; metadata = {}
    with retained.open(encoding='utf-8') as stream:
        parser = ObjectStream(stream)
        for key in parser.members():
            included = key not in {'artifact_identity','artifact_sha256'}
            if included:
                if not first: digest.update(b',')
                first = False; digest.update(canonical_bytes(key)); digest.update(b':')
            if key == 'records':
                parser.take('['); digest.update(b'['); index = 0
                while parser.peek() != ']':
                    if index: parser.take(','); digest.update(b',')
                    digest.update(canonical_bytes(parser.value())); index += 1
                parser.take(']'); digest.update(b']')
            else:
                value = parser.value(); metadata[key] = value
                if included: digest.update(canonical_bytes(value))
        assert not parser.peek()
    digest.update(b'}')
    assert digest.hexdigest() == metadata['artifact_sha256'] == artifact['artifact_sha256']
    assert artifact['artifact_identity'] == metadata['artifact_identity']
    proof = dict(identity=artifact['artifact_identity'], records=len(artifact['records']),
                 validation=artifact['validation'], elapsed=time.perf_counter()-t, canonical_parity=True)
    # Exercise the actual immutable writer on scratch, including warm replay/conflict.
    path = output/'signal_velocity.json'
    velocity.write_immutable(path, artifact)
    assert source_hash(path) == touched[str(retained)]
    proof['raw_byte_parity'] = True
    del artifact
    observe('observer_result_deleted')
    proof['gc_collected'] = gc.collect()
    observe('observer_after_gc')
    return proof


def consumers(source, output, touched, observe):
    """Actual read-only Owner handoff/completion and Thesis reporting consumers."""
    from bounded_artifact_stream import source_hash
    from tools.run_owner_daily import verify_daily_completion, verify_retained_daily_brief_for_handoff
    from stocklookup_core.research.thesis_production_runtime import read_product_report
    # Use the canonical Owner's configured default; override honors the runtime env.
    import os
    runtime = Path(os.environ.get('STOCK_LOOKUP_RUNTIME_ROOT',source.parent/'dashboard-runtime'))
    for p in (runtime/'bundle_manifest.json', source/'config/daily_research_session_input_registry.json'):
        touched[str(p)] = source_hash(p)
    completion = verify_daily_completion(source,runtime,session='2026-10-06')
    directory = completion['source']
    for p in directory.glob('*'):
        if p.is_file():touched[str(p)] = source_hash(p)
    touched[str(completion['record_path'])] = source_hash(completion['record_path'])
    for p in (source/'operations-review/canonical-post-close-v1/2026-10-06/enrichment/integrated_investment_decision_product.json',
              source/'operations-review/integrated-investment-decision-product-v1-20261006/integrated_investment_decision_product_artifact.json'):
        touched[str(p)] = source_hash(p)
    handoff = verify_retained_daily_brief_for_handoff(directory,'2026-10-06',root=source,
        expected_operation_identity=completion['operation_id'])
    observe('owner_m1_handoff_verified')
    reports=[]
    for family in ('thesis-evidence-t0-v1','thesis-evidence-current-v1'):
        manifests=list((source/'operations-review'/family/'2026-10-06').glob('*/manifest.json'))
        assert len(manifests) == 1
        for p in manifests[0].parent.glob('*'):
            if p.is_file():touched[str(p)] = source_hash(p)
        reports.append(read_product_report(manifests[0]))
    observe('thesis_reports_verified')
    gc.collect(); observe('consumer_after_gc')
    return dict(completion=dict(session=completion['session'], operation_id=completion['operation_id']),
                handoff={k:v for k,v in handoff.items() if k != 'brief_path'},thesis=reports)


def whole_tail(source, output, session, decision, operation, handoff, touched, observe, live_sources, *, downstream_only=False):
    from bounded_artifact_stream import source_hash, stream_artifact
    import prospective_decision_retention as retention
    import prospective_t0_seal_index as seal
    exact = live_sources['exact']
    history = live_sources['historical_context']
    observe('retained_acquisition_and_history_live')
    t = time.perf_counter()
    # A diagnostic reconstruction only: never replace/rebuild historical evidence.
    snapshot = retention.build_snapshot(session=session,
        operation_identity=operation['manifest']['operation_identity'],
        producer_run_identity=handoff.get('daily_producer_run_identity'),
        integrated_artifact=decision, exact_session_snapshot=exact)
    observe('t0_constructed')
    declared = handoff['prospective_decision_snapshot']['identity']
    assert snapshot['snapshot_identity'] == declared
    original = source/'operations-review/prospective-decision-retention-v1'/session/declared.split(':',1)[1]/'prospective_decision_snapshot.json'
    touched[str(original)] = source_hash(original)
    original_index = json.loads((original.parent/'prospective_t0_seal_index.json').read_bytes())
    for p in (original.parent/'prospective_t0_seal_index.json',original.parent/'prospective_t0_snapshot_write_receipt.json'):
        touched[str(p)] = source_hash(p)
    if downstream_only:
        receipt=json.loads((original.parent/'prospective_t0_snapshot_write_receipt.json').read_bytes())
        ref=dict(path=str(original.parent/'prospective_t0_seal_index.json'),artifact_identity=original_index['artifact_identity'],
                 write_receipt_identity=receipt['artifact_identity'])
    else:
        scratch = retention.write_immutable_snapshot(output, snapshot)
        assert source_hash(scratch) == touched[str(original)]
        observe('t0_scratch_written')
        ref = seal.from_snapshot(snapshot,scratch,created_at=original_index['index_created_at'],file_sha256=touched[str(original)])
        scratch_index = json.loads(Path(ref['path']).read_bytes())
        assert scratch_index == original_index
    seal.load_verified(ref,expected_snapshot_identity=declared,session=session)
    observe('seal_verified')
    proof = dict(t0_identity=declared, t0_byte_parity=not downstream_only, seal_index_parity=True,
                 t0_elapsed=time.perf_counter()-t)
    # Keep exact/history/T0 + caller IID/operation alive while observing, matching Daily lifetime.
    if not downstream_only: proof['observer'] = observer(source,output,touched,observe)
    # Reproduce the unchanged downstream full-velocity ingress with the live
    # kernel graph present (divergence then VolumeFlow are sequential consumers).
    from bounded_artifact_stream import record_mapping_digest
    velocity_path=source/'operations-review/multi-session-signal-velocity-v1.2'/session/'multi_session_signal_velocity_artifact.json'
    for number in range(2):
        velocity=json.loads(velocity_path.read_text(encoding='utf-8'))
        observe('downstream_velocity_parsed_'+str(number))
        body={k:v for k,v in velocity.items() if k not in {'artifact_identity','artifact_sha256'}}
        assert record_mapping_digest(body) == velocity['artifact_sha256']
        observe('downstream_velocity_verified_'+str(number))
        del body, velocity
        observe('downstream_velocity_released_'+str(number))
    del snapshot, exact, history
    observe('tail_graphs_deleted')
    return proof
