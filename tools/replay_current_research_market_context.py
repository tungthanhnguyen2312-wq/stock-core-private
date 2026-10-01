"""Bounded read-only market-context acceptance from an accepted decision checkpoint."""
from __future__ import annotations
import argparse
import copy
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import daily_session_level2_package as paths_module
import integrated_investment_decision_product as product
import market_wide_relative_volume_research as participation
import financial_analysis_product_projection as financial_projection
import canonical_daily_financial_v2_materialization as financial_materialization
import operational_fundamental_context_integration as operational
from canonical_post_close_pipeline import resolve_current_session_priority_queue
from ai_research_session_delivery import project_integrated_decision_for_ai_delivery
from replay_current_research_structural_conditions import changed_paths


def assert_thesis_attribution(before, after, prior_wrapper, wrapper, bindings):
    """Undo exactly the additive envelope, provenance and absence-as-counter correction."""
    assert product.decision_identity(after) == after['decision_identity']
    replacements = {wrapper['artifact_identity']: prior_wrapper['artifact_identity'],
                    wrapper['financial_analysis_product']['artifact_identity']: prior_wrapper['financial_analysis_product']['artifact_identity']}
    replacements.update(bindings)
    def normalize(value):
        if isinstance(value, dict):
            return {key: normalize(item) for key,item in value.items()
                    if key not in {'source_feature_context', 'thesis_context', 'evidence_gap_reason_codes'}}
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return replacements.get(value, value) if isinstance(value, str) else value
    normalized = normalize(after)
    normalized['decision_identity'] = before['decision_identity']
    normalized['current_research_decision_input']['provenance']['decision_identity'] = before['decision_identity']
    if 'FUNDAMENTAL_CONTEXT_ABSENT' in before['counter_thesis']:
        assert 'FUNDAMENTAL_CONTEXT_ABSENT' not in after['counter_thesis']
        assert 'FUNDAMENTAL_CONTEXT_ABSENT' in after['material_uncertainties']
        assert after['fundamental_synthesis']['evidence_gap_reason_codes'] == ['FUNDAMENTAL_CONTEXT_ABSENT']
        normalized['material_uncertainties'] = [x for x in normalized['material_uncertainties'] if x != 'FUNDAMENTAL_CONTEXT_ABSENT']
        normalized['current_research_decision_input']['provenance']['warnings'] = [x for x in normalized['current_research_decision_input']['provenance']['warnings'] if x != 'FUNDAMENTAL_CONTEXT_ABSENT']
        # Existing duplicate summaries carry the same absence code; restore each exact old list.
        for path in [('counter_thesis',), ('fundamental_counter',),
                     ('fundamental_synthesis','contradicting_reason_codes'),
                     ('evidence_axes','FUNDAMENTAL','contradicting_reason_codes'),
                     ('financial_composite_context','contradicting_reason_codes'),
                     ('current_research_decision_input','synthesis','weak_reason_codes')]:
            old, new = before, normalized
            for key in path[:-1]:
                old, new = old[key], new[key]
            if path[-1] in old:
                new[path[-1]] = copy.deepcopy(old[path[-1]])
    assert normalized == before, list(changed_paths(before, normalized))[:12]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retained-root', type=Path, required=True)
    parser.add_argument('--checkpoint-output', type=Path, required=True)
    parser.add_argument('--structural-checkpoint', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--coherence-acceptance', action='store_true')
    parser.add_argument('--participation-acceptance', action='store_true')
    parser.add_argument('--fundamental-thesis-acceptance', action='store_true')
    parser.add_argument('--engine-input', type=Path)
    args = parser.parse_args()
    retained, checkpoint, output = (p.resolve() for p in (args.retained_root, args.checkpoint_output, args.output_root))
    if any(output == p or p in output.parents for p in (retained, checkpoint, Path(__file__).resolve().parents[1])):
        raise ValueError('OUTPUT_MUST_BE_EXTERNAL')
    hashes = {}
    def load(path):
        raw = path.read_bytes()
        hashes[str(path)] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)
    before = load(checkpoint / 'integrated_investment_decision_product_artifact.json')
    assert product.content_identity(before)['artifact_identity'] == before['artifact_identity']
    session, stamp = before['session'], before['requested_at']
    paths = paths_module.session_artifact_paths(retained, session)
    wrapper = load(checkpoint / 'financial_peer_materialization_artifact.json')
    prior_wrapper = copy.deepcopy(wrapper)
    if args.fundamental_thesis_acceptance:
        if args.engine_input is None:
            raise ValueError('PINNED_ENGINE_REQUIRED')
        engine = load(args.engine_input)
        assert financial_projection._identity(engine)['artifact_identity'] == engine['artifact_identity'] == wrapper['financial_v2_engine_identity']
        compact = financial_projection.build_product_projection(financial_context=engine,
            product_tickers=sorted(before['records']), requested_at=wrapper['financial_analysis_product']['requested_at'])
        normalized = copy.deepcopy(compact)
        for row in normalized['records'].values():
            for fitness in (row.get('feature_fitness') or {}).values():
                fitness.pop('source_feature_context', None)
        normalized.update(financial_projection._identity(normalized, financial_projection.INTEGRATION_CONTRACT))
        assert normalized == wrapper['financial_analysis_product'], 'UNEXPLAINED_COMPACT_CHANGE'
        wrapper['financial_analysis_product'] = compact
        wrapper['financial_content_identity'] = compact['artifact_identity']
        wrapper.update(financial_materialization._identity(wrapper))
    snapshot = load(paths['exact_session_snapshot'])
    market = load(paths['sector_leadership'])
    queue, resolution = resolve_current_session_priority_queue(session,
        opportunity=load(paths['opportunity_prioritization']), triage=load(paths['session_triage']))
    assert queue is not None, resolution
    kwargs = dict(session=session, requested_at=stamp,
        technical_structure_artifact=load(args.structural_checkpoint / 'market_structure_breakout_v3_projection_artifact.json'),
        financial_analysis_artifact=wrapper['financial_analysis_product'],
        financial_peer_materialization_artifact=wrapper,
        current_valuation_artifact=load(paths['current_valuation_evaluated']),
        relative_volume_artifact=participation.build_artifact(candidates=sorted(snapshot['records']), records=snapshot['records'], session=session, requested_at=stamp),
        market_sector_artifact=market,
        legacy_decision_artifact=load(paths['opportunity_prioritization']), priority_queue_artifact=queue,
        momentum_artifact=load(paths['tactical_momentum_context']),
        tactical_confirmation_artifact=load(paths['tactical_confirmation_context']),
        tactical_boundaries_artifact=load(paths['tactical_confirmation_invalidation_boundaries']),
        corporate_intelligence_artifact=load(paths['corporate_intelligence_axis']),
        technical_coverage_disposition_artifact=load(paths['technical_coverage_disposition']),
        operational_fundamental_integration_artifact=load(paths['operational_fundamental_context_integration']),
        liquidity_research_artifact=load(paths['liquidity_research']),
        entity_applicability_artifact=load(paths['current_research_entity_applicability']))
    bindings = {}
    if args.fundamental_thesis_acceptance:
        bridge = kwargs['operational_fundamental_integration_artifact']
        assert bridge['source_artifact_identities']['financial_analysis'] == prior_wrapper['financial_analysis_product']['artifact_identity']
        old_identity = bridge['artifact_identity']
        bridge['source_artifact_identities']['financial_analysis'] = wrapper['financial_analysis_product']['artifact_identity']
        bridge.update(operational.content_identity(bridge))
        bindings[bridge['artifact_identity']] = old_identity
    after = product.build_artifact(**kwargs)
    assert after == product.build_artifact(**kwargs), 'NONDETERMINISTIC'
    assert set(before['records']) == set(after['records'])
    allowed = ('market_sector_context.market_breadth', 'evidence_axes.MARKET_SECTOR.context.market_breadth',
               'current_research_decision_input.dimensions.MARKET.market_breadth')
    if args.coherence_acceptance:
        allowed = ('evidence_axis_coherence', 'why_now',
                   'current_research_decision_input.synthesis.why_interesting.evidence_axis_coherence',
                   'priority_posture_reconciliation.integrated_posture_reason')
    if args.participation_acceptance:
        allowed = ('participation.source_observation', 'participation.reason_codes')
    changes = Counter()
    delivery = {}
    for ticker, record in after['records'].items():
        if args.fundamental_thesis_acceptance:
            assert_thesis_attribution(before['records'][ticker], record, prior_wrapper, wrapper, bindings)
        for path in changed_paths(before['records'][ticker], record):
            if not args.fundamental_thesis_acceptance:
                assert any(path == prefix or path.startswith(prefix + '.') for prefix in allowed), (ticker, path)
            changes[path] += 1
        view = project_integrated_decision_for_ai_delivery(record, integrated_identity=after['artifact_identity'])
        assert view['evidence_axes'] == record['evidence_axes']
        assert view['current_research_decision_input'] == record['current_research_decision_input']
        assert view['is_actionable'] is False
        delivery[ticker] = view
    registry = load(retained / 'config/daily_research_session_input_registry.json')
    selected_flow = registry['sessions'][session].get('market_flow_positioning')
    summary = dict(session=session, input_count=len(before['records']), output_count=len(after['records']),
        zero_silent_drops=True, unexplained_changes=0, deterministic=True,
        before_identity=before['artifact_identity'], after_identity=after['artifact_identity'],
        decision_identity_changes=sum(before['records'][t]['decision_identity'] != r['decision_identity'] for t,r in after['records'].items()),
        changed_paths=dict(changes),
        market_observation=market['market'],
        breadth_status=dict(Counter(r['market_sector_context']['market_breadth']['status'] for r in after['records'].values())),
        sector_status=dict(Counter(r['market_sector_context']['sector_leadership_status'] for r in after['records'].values())),
        participation_status=dict(Counter(r['participation']['status'] for r in after['records'].values())),
        flow_selection=selected_flow, flow_status='NO_GOVERNED_SESSION_INPUT' if selected_flow is None else 'SELECTED',
        provider_calls=0, authority_effect='NONE', posture_changes=0,
        why_changes=sum(before['records'][t]['why_now'] != r['why_now'] for t,r in after['records'].items()),
        coherence_changes=sum(before['records'][t]['evidence_axis_coherence'] != r['evidence_axis_coherence'] for t,r in after['records'].items()),
        coherence_before=dict(Counter(r['evidence_axis_coherence']['state'] for r in before['records'].values())),
        coherence_after=dict(Counter(r['evidence_axis_coherence']['state'] for r in after['records'].values())),
        counter_changes=sum(before['records'][t]['counter_thesis'] != r['counter_thesis'] for t,r in after['records'].items()),
        retained_input_hashes_unchanged=hashes)
    for path, digest in hashes.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest, path
    traces = {t: {k: after['records'][t].get(k) for k in ('market_sector_context','participation','research_action_posture','counter_thesis','evidence_axis_coherence')}
              for t in ('AAA','HPG','VCB','SSI','POW','PVD','VNM','F88','ACE') if t in after['records']}
    output.mkdir(parents=True, exist_ok=False)
    for name, value in [('integrated_investment_decision_product_artifact.json',after),
                        ('integrated_decision_delivery_records.json',delivery),('market_context_summary.json',summary),
                        ('market_context_traces.json',traces),('financial_peer_materialization_artifact.json',wrapper)]:
        (output / name).write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('retained_input_hashes_unchanged','market_observation')},indent=2))

if __name__ == '__main__':
    main()
