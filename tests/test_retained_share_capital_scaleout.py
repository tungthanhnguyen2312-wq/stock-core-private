"""Real retained cells and adversarial use boundaries for the bounded note extension."""
import copy
import json
from pathlib import Path

import pytest

from stocklookup_core.evidence.current_common_shares_official_evidence_acquisition import qualify_retained_share_capital_note
from stocklookup_core.research.shareholder_economics import project_context

INPUTS = json.loads((Path(__file__).parent / 'fixtures/retained_share_capital_scaleout_v1.json').read_bytes())['qualification_inputs']
NOW = '2026-10-24T23:59:59+07:00'


def note(index):
    return qualify_retained_share_capital_note(**copy.deepcopy(INPUTS[index]))


@pytest.mark.parametrize('index,count', [(0, 6), (1, 6), (2, 9)])
def test_real_source_receipts_replay_into_existing_engine(index, count):
    n = note(index)
    c = project_context(ticker=n['ticker'], cutoff=NOW, retained_common_share_notes=[n])
    assert len(c['claims']) == count and not c['rejected']
    assert c['current_outstanding_shares'] is None
    assert c['price_adjustment_factor'] is None and not c['historical_pit_eligible']
    assert c['authority_effect'] == c['vote_effect'] == 'NONE'
    assert c['share_capital_research']['strict_per_share_use'] == 'BLOCKED_RESEARCH_ONLY'
    assert all(r['source_citation']['selected_tokens'] and r['published_at'] is None for r in c['claims'])


def test_pnj_endpoint_growth_is_not_continuity_or_ownership_dilution():
    c = project_context(ticker='PNJ', cutoff=NOW, retained_common_share_notes=[note(0)])
    points = {(r['kind'], r['effective_date']): r['value'] for r in c['claims']}
    assert points['OUTSTANDING_SHARES', '2025-12-31'] == 341149107
    assert points['OUTSTANDING_SHARES', '2024-12-31'] == 337905217
    assert points['ISSUED_SHARES', '2025-12-31'] == 341318666
    assert points['TREASURY_SHARES', '2025-12-31'] == 169559
    changes = c['share_capital_research']['endpoint_changes']
    assert sorted(r['change'] for r in changes) == [0, 3243890, 3243890]
    assert all(r['ownership_dilution'] == 'UNKNOWN' and r['continuity_status'] == 'UNKNOWN_BETWEEN_OBSERVATIONS' for r in changes)


def test_pvd_share_cells_never_select_adjacent_vnd_cells_or_eps():
    n = note(1)
    assert {r['value'] for r in n['claims']} == {556296006, 416000, 555880006}
    assert all(r['unit'] == 'shares' and r['scope'] == 'issuer_self_held_treasury' for r in n['claims'])
    assert all('EPS' not in r['kind'] for r in n['claims'])


def test_ssi_notice_preserves_total_voting_and_bonus_execution():
    n = note(2)
    values = {(r['kind'], r['effective_date']): r['value'] for r in n['claims']}
    assert values['TOTAL_SHARES', '2026-08-18'] == 3003293801
    assert values['VOTING_SHARES', '2026-08-18'] == 3001302333
    assert values['TREASURY_SHARES', '2026-08-18'] == 1991468
    assert values['CHARTER_CAPITAL', '2026-08-18'] == 30032938010000
    assert values['VOTING_SHARES', '2026-06-15'] == 2501097752
    c = project_context(ticker='SSI', cutoff=NOW, retained_common_share_notes=[n])
    event, = c['share_capital_research']['event_lifecycles']
    assert event['state'] == 'EXECUTED' and event['consideration'] == 'BONUS_FROM_EQUITY'
    assert event['value'] == 500204581 and event['issuance_end_date'] == '2026-08-18'
    assert not any(r['kind'] in {'ISSUED_SHARES', 'OUTSTANDING_SHARES', 'FINANCING_PROCEEDS'} for r in c['claims'])
    assert all(r.get('ex_date') is None and r.get('first_trading_date') is None for r in c['claims'])


@pytest.mark.parametrize('index', range(3))
@pytest.mark.parametrize('mutation', ['value', 'scope', 'date', 'stage', 'class'])
def test_caller_cannot_reinterpret_source_owned_receipt(index, mutation):
    n = note(index)
    key, value = {'value': ('value', 1), 'scope': ('scope', 'consolidated_subsidiary_held'),
        'date': ('effective_date', '2026-10-23'), 'stage': ('state', 'APPROVED_PROPOSAL'),
        'class': ('share_class', 'preferred')}[mutation]
    n['claims'][0][key] = value
    c = project_context(ticker=n['ticker'], cutoff=NOW, retained_common_share_notes=[n])
    assert not c['claims'] and c['rejected'][0]['reason_codes'] == ['RETAINED_NOTE_RECEIPT_MISMATCH']


@pytest.mark.parametrize('index', range(3))
def test_later_known_source_does_not_enter_old_session(index):
    n = note(index)
    c = project_context(ticker=n['ticker'], cutoff='2026-10-23T15:00:00+07:00', retained_common_share_notes=[n])
    assert not c['claims'] and c['rejected'][0]['reason_codes'] == ['SOURCE_NOT_KNOWN_AT_CUTOFF']


@pytest.mark.parametrize('index', range(3))
def test_qualification_cannot_backdate_knowledge(index):
    args = copy.deepcopy(INPUTS[index]); args['knowledge_available_at'] = '2025-01-01T00:00:00Z'
    with pytest.raises(ValueError, match='KNOWLEDGE_TIME_BACKDATING_REFUSED'):
        qualify_retained_share_capital_note(**args)


@pytest.mark.parametrize('index', [0, 1])
def test_ambiguous_amount_is_not_ocr_repaired(index):
    args = copy.deepcopy(INPUTS[index])
    cell = next(t for t in args['materialization']['tokens'] if t['text'] == ('341,318,666' if index == 0 else '556.296.006')
                and (2100 <= t['top'] < 2145 if index == 0 else 1870 <= t['top'] < 1910))
    cell['text'] = cell['text'].replace('6', 'O', 1)
    with pytest.raises(ValueError, match='CAPITAL_NUMERIC_CELL_AMBIGUOUS'):
        qualify_retained_share_capital_note(**args)


@pytest.mark.parametrize('index', [0, 1])
def test_assurance_is_source_bound_not_an_audited_annotation(index):
    args = copy.deepcopy(INPUTS[index]); args['assurance']['document_sha256'] = 'a' * 64
    with pytest.raises(ValueError, match='AUDITOR_EVIDENCE_NOT_QUALIFIED'):
        qualify_retained_share_capital_note(**args)


def test_ssi_is_issuer_notice_not_auditor_qualification():
    args = copy.deepcopy(INPUTS[2]); args['assurance'] = INPUTS[0]['assurance']
    with pytest.raises(ValueError, match='ISSUER_NOTICE_IS_NOT_AUDITOR_ASSURANCE'):
        qualify_retained_share_capital_note(**args)


def test_unreviewed_layout_never_inherits_issuer_wide_qualification():
    args = copy.deepcopy(INPUTS[0]); args['document']['sha256'] = args['materialization']['document_sha256'] = 'b' * 64
    with pytest.raises(ValueError, match='CAPITAL_NOTE_LAYOUT_NOT_REVIEWED'):
        qualify_retained_share_capital_note(**args)


def test_unknown_publication_adapter_does_not_relax_generic_receipts():
    n = note(0)
    c = project_context(ticker='PNJ', cutoff=NOW, observations=n['claims'])
    assert not c['claims'] and all('SOURCE_NOT_KNOWN_AT_CUTOFF' in r['reason_codes'] for r in c['rejected'])


@pytest.mark.parametrize('mutation,accepted', [('', True), ('host', False), ('case', False), ('clock', False), ('bytes', False)])
def test_inspection_multiple_roots_and_exact_note_receipt_binding(tmp_path, monkeypatch, mutation, accepted):
    """Synthetic byte routing only: no fake PDF qualifies an economic fact."""
    from tools import replay_corporate_shareholder_economics as tool
    from stocklookup_core.research import shareholder_economics as engine
    monkeypatch.setattr(tool, 'ROOT', tmp_path)
    raw_root = tmp_path / 'retained'; raw_root.mkdir()
    raw = raw_root / 'original.pdf'; raw.write_bytes(b'synthetic routing test, not financial evidence')
    sha = tool.digest(raw)
    url = 'https://www.pvdrilling.com.vn/exact name.pdf'
    document = dict(ticker='PVD', sha256=sha, canonical_url=url, observed_at='2026-10-24T09:00:00Z', published_at=None)
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'records': [document | dict(acquisition_status='retained', relative_path='original.pdf')]}))
    index = tmp_path / 'index.json'
    index.write_text(json.dumps(dict(report_known_at='2026-10-24T09:00:00Z', events=[], continuity_points=[], unresolved_gaps=[],
        source_manifest=dict(documents=[dict(source_id='PVD_TEST', issuer='PVD', sha256=sha, url=url.replace(' ', '%20'))]))))
    n = dict(contract_version='retained_share_capital_note/v1', ticker='PVD', document=copy.deepcopy(document), citation_id='routing-only')
    if mutation == 'host': n['document']['canonical_url'] = url.replace('pvdrilling', 'untrusted')
    if mutation == 'case': n['document']['canonical_url'] = url.replace('exact', 'EXACT')
    if mutation == 'clock': n['document']['observed_at'] = '2026-10-23T09:00:00Z'
    if mutation == 'bytes': raw.write_bytes(b'changed original')
    notes = tmp_path / 'notes.json'; notes.write_text(json.dumps(dict(notes=[n])))
    seen = []
    original_project = engine.project_context
    def route_only(**kwargs):
        seen.extend(kwargs.pop('retained_common_share_notes'))
        return original_project(**kwargs)  # deliberately admit no facts
    monkeypatch.setattr(engine, 'project_context', route_only)
    result = tool.inspect_research(candidate_index=index, output=tmp_path/'.stocklookup/scratch/result', cutoff=NOW,
        tickers='PVD', share_note=[notes], original_root=[raw_root], original_manifest=[manifest])
    assert bool(seen) is accepted and result['admitted_observations'] == 0
