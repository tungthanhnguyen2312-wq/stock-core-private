"""Synthetic constructions over bounded public October 9 representative inputs.

No retained runtime paths, Daily execution or historical artifact rewriting.
"""
import copy
import json
from pathlib import Path

import pytest

import canonical_daily_financial_v2_materialization as financial
import stocklookup_core.decision.daily_integrated_decision_brief as brief
import daily_opportunity_decision_queue as queue
import stocklookup_core.decision.integrated_investment_decision_product as iid
from _integrated_decision_fixture import integrated_decision
from test_daily_opportunity_decision_queue import _opportunity, _triage
from test_research_posture_v2_policy import BEAR, FIRED, policy_case

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/daily_research_semantic_oct09.json').read_text(encoding='utf-8'))
SESSION = FIXTURE['session']


@pytest.mark.parametrize('ticker', ['HPG', 'EVF', 'FPT', 'PVD', 'VNM', 'VCB', 'SSI', 'PNJ'])
def test_adverse_explanation_names_only_observed_bos_or_downtrend(ticker):
    source = FIXTURE['records'][ticker]
    before = copy.deepcopy(source)
    artifact = integrated_decision(SESSION, [ticker], tactical_records={ticker: source['tactical']},
                                   currency_by_ticker={ticker: 'CURRENT_SESSION'})
    row = artifact['records'][ticker]
    assert row['research_action_posture'] == source['iid']['research_action_posture'] == 'AVOID'
    assert row['posture_condition_class'] == 'BEARISH_STRUCTURE_ADVERSE'
    has_bos = source['tactical']['bos_state'] == 'BEARISH_BOS_DETECTED_BY_RULE'
    assert ('bearish bos' in row['why_now'].lower()) == has_bos
    if not has_bos:
        assert 'Qualified downtrend without a breakout or fired trigger' in row['why_now']
        assert 'confirmed lower lows' not in row['why_now']
    assert row['decision_identity'] == iid.decision_identity(row)
    assert iid.content_identity(artifact)['artifact_identity'] == artifact['artifact_identity']
    # Explanation changes the content hash, never the decision identity field set.
    changed = copy.deepcopy(row)
    changed['why_now'] = 'different prose'
    assert iid.decision_identity(changed) == row['decision_identity']
    assert source == before


@pytest.mark.parametrize('changes,expected', [
    ({'market_structure_state': 'DOWNTREND', 'bos_state': None}, 'BEARISH_STRUCTURE_ADVERSE'),
    ({'market_structure_state': 'DOWNTREND', 'bos_state': 'BULLISH_BOS_DETECTED_BY_RULE'}, 'BEARISH_STRUCTURE_ADVERSE'),
    ({**FIRED, **BEAR}, 'BEARISH_STRUCTURE_ADVERSE'),
    ({**FIRED, 'market_structure_state': 'DOWNTREND'}, 'EARLY_REVERSAL_AWAITING_HIGHER_LOW'),
    ({'eligible': False, **BEAR}, 'UNQUALIFIED_TACTICAL_STRUCTURE'),
])
def test_synthetic_bos_presence_does_not_change_released_precedence(changes, expected):
    posture, why, _, klass = policy_case(('SYN', 'IMPROVING', changes, {}, {}, expected))
    assert klass == expected and posture == iid.POSTURE_CLASS_COMPATIBILITY[expected]
    assert ('bearish bos' in why.lower()) == (expected == 'BEARISH_STRUCTURE_ADVERSE' and changes.get('bos_state') == BEAR['bos_state'])


@pytest.mark.parametrize('ticker', ['PAN', 'VCB', 'PVT', 'VPB'])
def test_surface_passes_iid_while_queue_preserves_independent_lens(ticker):
    source = FIXTURE['records'][ticker]
    q = source['queue']
    opportunity_row = {**q, 'ticker': ticker, 'priority_tier': q['research_priority_tier'],
                       'lane_priority': q['lane_specific_priority'],
                       'content_identity': q['opportunity_record_content_identity']}
    opportunity = _opportunity({ticker: opportunity_row})
    opportunity['research_session'] = SESSION
    result = queue.build(opportunity=opportunity, triage=_triage([]))
    queue.replay(result)
    qr = result['records'][ticker]
    assert all(qr[k] == q[k] for k in ['entry_action', 'tactical_state', 'entry_relevant', 'research_priority_tier', 'source_input_identities'])
    assert 'independent watchlist_tactical_entry_classifier lens' in qr['authority_note']
    assert 'sole posture authority' in qr['authority_note']
    a = integrated_decision(SESSION, [ticker], tactical_records={ticker: source['tactical']},
                            currency_by_ticker={ticker: 'CURRENT_SESSION'})
    b = integrated_decision(SESSION, [ticker], tactical_records={ticker: source['tactical']},
                            currency_by_ticker={ticker: 'CURRENT_SESSION'}, priority_queue=result)
    surface = iid.decision_surface_index(b)['rows'][0]
    row = b['records'][ticker]
    for key in ['research_action_posture', 'posture_condition_class', 'research_action_policy_version', 'evidence_currency']:
        assert surface[key] == row[key] == source['surface'][key] == source['iid'][key]
    for key in ['research_action_posture', 'posture_condition_class', 'trigger', 'invalidation', 'decision_identity']:
        assert a['records'][ticker][key] == row[key]
    assert qr['entry_action'] != row['research_action_posture']


@pytest.mark.parametrize('known_at,status', [
    ('2026-09-05T00:00:00+07:00', 'NON_CALENDAR_FISCAL_PERIOD_KNOWN_BY_SESSION'),
    (None, 'KNOWLEDGE_TIME_UNPROVEN_FAIL_CLOSED'),
    ('2026-10-10T00:00:00+07:00', 'KNOWLEDGE_TIME_UNPROVEN_FAIL_CLOSED'),
])
def test_q4_label_is_not_published_calendar_q4_or_reporting_calendar(known_at, status):
    engine = {'records': {t: {'features': {'net_margin': {'period_identity': ['2026-Q4']}},
                            'lineage': {'source_identities': {'period_semantics_knowledge_time': known_at}}}
                          for t in ['ITD', 'TCH']}}
    before = copy.deepcopy(engine)
    earliest, latest = financial._observed_period_range(engine)
    assert earliest == latest == '2026-Q4'
    context = financial.observed_period_label_context(engine, decision_session=SESSION, latest_period=latest)
    assert context['published_calendar_evidence_as_of_period'] is None
    assert context['is_publication_cutoff'] is context['is_reporting_calendar_context'] is False
    assert {r['status'] for r in context['observations']} == {status}
    if known_at and known_at.startswith('2026-09-05'):
        assert {r['calendar_period'] for r in context['observations']} == {'UNRESOLVED_NO_GOVERNED_FISCAL_YEAR_REGISTRY'}
    projected = brief.build_financial_evidence_context({'financial_evidence_as_of_period': latest,
        'latest_observed_financial_period_label': latest, 'financial_evidence_period_label_context': context})
    assert projected['financial_evidence_period_label_context'] == context
    assert projected['latest_observed_financial_period_label'] == '2026-Q4'
    assert 'not a publication cutoff' in projected['note']
    assert engine == before


def test_completed_calendar_label_and_absent_evidence_do_not_invent_publication():
    engine = {'records': {'HPG': {'features': {'margin': {'period_identity': ['2026-Q2']}}}}}
    ctx = financial.observed_period_label_context(engine, decision_session=SESSION, latest_period='2026-Q2')
    assert ctx['observations'][0]['status'] == 'CALENDAR_READING_NOT_AFTER_SESSION'
    assert ctx['published_calendar_evidence_as_of_period'] is None
    assert financial._observed_period_range({'records': {}}) == (None, None)
    assert financial.observed_period_label_context({'records': {}}, decision_session=SESSION, latest_period=None)['observations'] == []
    legacy = brief.build_financial_evidence_context({'financial_evidence_as_of_period': '2026-Q4'})
    assert legacy['latest_observed_financial_period_label'] == '2026-Q4'
    assert legacy['financial_evidence_period_label_context']['published_calendar_evidence_as_of_period'] is None


def test_session_wrapper_exposes_label_context_without_changing_engine(monkeypatch):
    from types import SimpleNamespace
    engine = {'artifact_identity': 'financial_analysis_context/v2:synthetic', 'records': {
        'ITD': {'features': {'net_margin': {'period_identity': ['2026-Q4']}},
                'lineage': {'source_identities': {'period_semantics_knowledge_time': '2026-09-05'}}}}}
    before = copy.deepcopy(engine)
    monkeypatch.setattr(financial, 'build_compact_product', lambda **kwargs: {'artifact_identity': 'compact:synthetic'})
    monkeypatch.setattr(financial, 'build_peer_context', lambda **kwargs: {})
    authority = SimpleNamespace(to_manifest=lambda: {'authority_version': 'synthetic'})
    output = financial.build_session_artifact(root=Path('.'), decision_session=SESSION,
        product_tickers=['ITD'], requested_at=SESSION, engine_artifact=engine, authority=authority)
    assert output['latest_observed_financial_period_label'] == output['financial_evidence_as_of_period'] == '2026-Q4'
    context = output['financial_evidence_period_label_context']
    assert context['observations'][0]['status'] == 'NON_CALENDAR_FISCAL_PERIOD_KNOWN_BY_SESSION'
    assert context['published_calendar_evidence_as_of_period'] is None
    assert output['financial_v2_engine_identity'] == engine['artifact_identity']
    assert output['artifact_identity'] == financial._identity(output)['artifact_identity']
    assert brief.build_financial_evidence_context(output)['financial_evidence_period_label_context'] == context
    assert engine == before
