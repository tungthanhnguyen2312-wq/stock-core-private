"""Read-only acceptance of scenario roles from exact canonical retained inputs."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types
from collections import Counter
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import daily_session_level2_package as paths_module
import current_evidence_bound_scenario as scenario
import polymorphic_current_strategy_classification as strategy
import stocklookup_core.decision.current_opportunity_prioritization as opportunity
from stocklookup_core.decision.current_daily_decision_research_product import _card
from ai_research_session_delivery import _compact_context
from replay_current_research_structural_conditions import changed_paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retained-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--baseline-ref', required=True)
    args = parser.parse_args()
    root, output = args.retained_root.resolve(), args.output_root.resolve()
    repo = Path(__file__).resolve().parents[1]
    if any(output == p or p in output.parents for p in (root, repo)):
        raise ValueError('OUTPUT_MUST_BE_EXTERNAL')
    paths = paths_module.session_artifact_paths(root, '2026-09-30')
    hashes = {}
    def load(key):
        path = paths[key]
        raw = path.read_bytes()
        hashes[str(path)] = hashlib.sha256(raw).hexdigest()
        return json.loads(raw)
    before = load('scenario')
    inputs = {name: load(key) for name, key in {
        'descriptive':'descriptive_research','tactical':'tactical_classifier',
        'peer_relative':'peer_relative','fundamental':'fundamental',
        'valuation':'valuation','triage':'session_triage','catalyst':'catalyst',
        'screening':'screening_foundation','corporate_intelligence':'corporate_intelligence'}.items()}
    baseline = types.ModuleType('retained_scenario_baseline')
    source = subprocess.check_output(['git','show',args.baseline_ref+':current_evidence_bound_scenario.py'], cwd=repo, text=True)
    exec(compile(source, '<pinned scenario baseline>', 'exec'), baseline.__dict__)
    assert baseline.build(**inputs) == before, 'RETAINED_BASELINE_INPUT_MISMATCH'
    after = scenario.build(**inputs)
    assert after == scenario.build(**inputs), 'NONDETERMINISTIC'
    assert before['source_artifact_identities'] == after['source_artifact_identities']
    assert set(before['records']) == set(after['records']) and len(after['records']) == 1683
    changes = Counter()
    disposition_tickers = []
    delivery = {}
    for ticker, row in after['records'].items():
        old = before['records'][ticker]
        normalized = copy.deepcopy(row)
        for name, driver in normalized['scenario_drivers'].items():
            assert driver['evidence'] == old['scenario_drivers'][name]['evidence']
            assert driver['limitations'] == old['scenario_drivers'][name]['limitations']
            if name in {'MARKET_CONTEXT','TECHNICAL','TACTICAL','PEER_RELATIVE','FUNDAMENTAL','DATA_QUALITY'}:
                driver['status'] = old['scenario_drivers'][name]['status']
        for case in ('bear_case','base_case','bull_case'):
            normalized[case]['data_gaps'] = old[case]['data_gaps']
            if 'driver_states' in normalized[case]:
                normalized[case]['driver_states'] = old[case]['driver_states']
            assert row[case]['case_id'] == old[case]['case_id']
            assert row[case]['probability_status'] == 'UNKNOWN_UNCALIBRATED'
        assert row['bear_case']['invalidation'] is None
        assert row['bear_case']['required_confirmations'] == old['bear_case']['required_confirmations']
        normalized['bear_case']['invalidation'] = old['bear_case']['invalidation']
        normalized['bear_case'].pop('invalidation_status')
        normalized['key_driver_conflicts'] = old['key_driver_conflicts']
        if old['scenario_disposition'] != row['scenario_disposition']:
            assert old['scenario_disposition'] == 'SCENARIO_READY' and row['scenario_disposition'] == 'SCENARIO_PARTIAL'
            assert row['fundamental_context']['trajectory_status'] == 'UNAVAILABLE'
            disposition_tickers.append(ticker)
            normalized['scenario_disposition'] = old['scenario_disposition']
        assert normalized == old, (ticker, list(changed_paths(old, normalized)))
        changes.update(changed_paths(old, row))
        view = _compact_context(ticker, {'scenario':after}, {})['scenario']
        card = _card(ticker, inputs['tactical']['records'][ticker], None, None, None, row)
        for case in ('bear_case','base_case','bull_case'):
            assert view[case] == row[case] == card['scenario'][case]
        assert view['source_artifact_identity'] == after['artifact_identity'] and view['is_actionable'] is False
        delivery[ticker] = view
    strategy_inputs = {k:inputs[k] for k in ('descriptive','tactical','peer_relative','fundamental','valuation','corporate_intelligence')}
    old_strategy = strategy.build(**strategy_inputs, scenario=before)
    new_strategy = strategy.build(**strategy_inputs, scenario=after)
    strategy_changes = Counter()
    for ticker, row in new_strategy['records'].items():
        old = old_strategy['records'][ticker]
        assert row['eligible_strategy_ids'] == old['eligible_strategy_ids']
        for name, value in row['strategies'].items():
            assert value['status'] == old['strategies'][name]['status']
        allowed = ('strategy_record_id','scenario_context.scenario_disposition')
        for path in changed_paths(old, row):
            assert path in allowed or path.endswith('.scenario_relationship.scenario_disposition'), (ticker,path)
            strategy_changes[path] += 1
    opp_inputs = {k:inputs[k] for k in ('screening','tactical','fundamental','descriptive')}
    opp_inputs.update(official_universe=load('official_universe'),event_context=load('official_event_context'),peer=inputs['peer_relative'])
    old_opp = opportunity.build(**opp_inputs,strategy=old_strategy,scenario=before)
    new_opp = opportunity.build(**opp_inputs,strategy=new_strategy,scenario=after)
    priority_changes = []
    for ticker, row in new_opp['records'].items():
        old = old_opp['records'][ticker]
        normalized = copy.deepcopy(row)
        normalized['source_input_identities'] = old['source_input_identities']
        normalized['content_identity'] = old['content_identity']
        if ticker in disposition_tickers:
            for key in ('scenario_status','priority_tier','lane_priority','priority_reasons','blocking_reasons'):
                normalized[key] = old[key]
        assert normalized == old, (ticker,list(changed_paths(old,normalized)))
        if row['priority_tier'] != old['priority_tier']:
            assert ticker in disposition_tickers and old['priority_tier']=='PRIORITY_NOW' and row['priority_tier']=='SETUP_WATCH'
            priority_changes.append({'ticker':ticker,'before':old['priority_tier'],'after':row['priority_tier']})
    summary = dict(input_count=1683, output_count=1683, deterministic=True, unexplained_changes=0,
        before_identity=before['artifact_identity'],after_identity=after['artifact_identity'],
        before_coverage=before['coverage'],after_coverage=after['coverage'],changed_paths=dict(changes),
        disposition_changes=disposition_tickers,strategy_eligibility_changes=0,strategy_changed_paths=dict(strategy_changes),
        official_priority_count=1507,priority_changes=priority_changes,delivery_cases_preserved=1683,
        before_driver_statuses={n:dict(Counter(r['scenario_drivers'][n]['status'] for r in before['records'].values())) for n in scenario.DRIVER_TYPES},
        after_driver_statuses={n:dict(Counter(r['scenario_drivers'][n]['status'] for r in after['records'].values())) for n in scenario.DRIVER_TYPES},
        duplicated_bear_invalidation_before=sum(bool(r['bear_case']['invalidation']) and r['bear_case']['invalidation'] in r['bear_case']['required_confirmations'] for r in before['records'].values()),
        duplicated_bear_invalidation_after=0,provider_calls=0,authority_effect='NONE',retained_input_hashes_unchanged=hashes)
    for path,digest in hashes.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest
    output.mkdir(parents=True,exist_ok=False)
    traces = {t:{'before':before['records'][t],'after':after['records'][t],'delivery':delivery[t]} for t in sorted(set(disposition_tickers+['HPG','VCB','SSI','ACE','AAA'])) if t in after['records']}
    for name,value in [('scenario_artifact.json',after),('scenario_delivery_records.json',delivery),('scenario_acceptance_summary.json',summary),('scenario_traces.json',traces),('strategy_artifact.json',new_strategy),('opportunity_artifact.json',new_opp)]:
        (output/name).write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('retained_input_hashes_unchanged','changed_paths','strategy_changed_paths')},indent=2))

if __name__ == '__main__':
    main()
