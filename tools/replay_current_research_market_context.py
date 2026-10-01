"""Bounded read-only market-context acceptance from an accepted decision checkpoint."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import daily_session_level2_package as paths_module
import integrated_investment_decision_product as product
import market_wide_relative_volume_research as participation
from canonical_post_close_pipeline import resolve_current_session_priority_queue
from ai_research_session_delivery import project_integrated_decision_for_ai_delivery
from replay_current_research_structural_conditions import changed_paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retained-root', type=Path, required=True)
    parser.add_argument('--checkpoint-output', type=Path, required=True)
    parser.add_argument('--structural-checkpoint', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--coherence-acceptance', action='store_true')
    parser.add_argument('--participation-acceptance', action='store_true')
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
        for path in changed_paths(before['records'][ticker], record):
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
        coherence_after=dict(Counter(r['evidence_axis_coherence']['state'] for r in after['records'].values())), counter_changes=0,
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
