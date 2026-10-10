"""Retained HPG note and fail-closed listed/ordinary/knowledge/continuity semantics."""
import json
from pathlib import Path

import pytest

from current_common_shares_official_evidence_acquisition import qualify_retained_common_share_note
from current_common_shares_authority import resolve_ticker_share_authority, reconcile_subsequent_events
from share_basis_event_promotion import entry_verdict
from tests.test_b1_share_basis_event_promotion import ledger_entry

ROOT = Path(__file__).resolve().parents[1]


def observation():
    return json.loads((ROOT / 'derived/hpg-common-share-evidence-v1/share_observation.json').read_text(encoding='utf8'))


def inputs():
    o = observation()
    return {
        'document': {'sha256': o['document_sha256'], 'ticker': 'HPG', 'reporting_period': '2025',
            'observed_at': o['observed_at'], 'canonical_url': o['source_url'], 'document_id': o['evidence_id']},
        'materialization': {'document_sha256': o['document_sha256'], 'page_number': 41, 'rotation': 270,
            'rendered_image_sha256': o['citation']['rendered_image_sha256'],
            'tokens': o['citation']['source_tokens'] + o['citation']['date_tokens']},
        'assurance': o['assurance_evidence'], 'effective_date': '2025-12-31',
        'knowledge_available_at': o['knowledge_available_at'],
    }


def test_retained_common_row_is_exact_dated_and_does_not_extend_coverage():
    result = qualify_retained_common_share_note(**inputs())
    assert result['value'] == 7675465855
    assert result['identity'] == 'common_shares_outstanding'
    assert result['coverage_through'] == result['effective_date'] == '2025-12-31'
    assert result['published_at'] is None
    assert result['document_sha256'] == 'f38c5f75becf7d3f145d27183eec81f119fd4f75e378b983a2763ddc3f7e0c07'


@pytest.mark.parametrize('change', ['hash', 'issuer', 'date', 'assurance', 'backdate', 'class', 'numeric', 'column', 'conflict'])
def test_note_rejects_corruption_without_ocr_repair(change):
    args = inputs()
    if change == 'hash': args['materialization']['document_sha256'] = '0' * 64
    if change == 'issuer': args['document']['ticker'] = 'PNJ'
    if change == 'date': args['effective_date'] = '2026-12-31'
    if change == 'assurance': args['assurance']['state'] = 'UNKNOWN'
    if change == 'backdate': args['knowledge_available_at'] = '2026-01-01T00:00:00Z'
    ts = args['materialization']['tokens']
    if change == 'class':
        for t in ts:
            if t['text'] == 'thông': t['text'] = 'UNKNOWN'
    if change == 'column':
        for t in ts:
            if t['text'] == 'cuối': t['text'] = 'đầu'
    if change in {'numeric', 'conflict'}:
        cell = next(t for t in ts if t['text'] == '7.675.465.855')
        cell['text'] = '7.675.465.85S' if change == 'numeric' else '7.675.465.854'
    with pytest.raises(ValueError): qualify_retained_common_share_note(**args)


@pytest.mark.parametrize('identity', ['listed_shares', 'issued_shares', 'registered_for_trading_shares', None])
def test_executed_listing_and_other_share_concepts_cannot_promote(identity):
    row = ledger_entry(share_count_identity=identity)
    assert entry_verdict(row)['reason'] == 'common_outstanding_share_semantics_not_proven'


def test_trading_eligibility_does_not_establish_execution_and_fractional_counts_fail():
    assert not entry_verdict(ledger_entry(payment_or_execution_date=None))['promotable']
    assert not entry_verdict(ledger_entry(shares_after=2000.5))['promotable']


def test_later_known_note_cannot_enter_completed_cutoff_or_historical_point_session():
    for session in ('2026-10-07', '2025-12-31'):
        result = resolve_ticker_share_authority('HPG', session=session, official_common=observation())
        assert result['authority_tier'] == 'UNAVAILABLE'
        assert result['value'] is None
        assert result['blockers'] == ['SHARE_OBSERVATION_NOT_KNOWN_AT_CUTOFF']


def test_historical_observation_reaches_consumers_with_exact_gap_and_no_current_valuation():
    from stocklookup_core.valuation.market_wide_current_valuation_input_scaleout import _share_from_authority_record
    from current_research_decision_packet import _valuation
    from ai_research_session_delivery import _valuation_handoff
    o = observation()
    record = resolve_ticker_share_authority('HPG', session='2026-10-07', official_common=o,
        knowledge_cutoff=o['knowledge_available_at'])
    assert record['authority_tier'] == 'QUALIFIED_OFFICIAL_ANCHOR_NOT_CURRENT'
    assert not record['coverage_through_session']
    share = _share_from_authority_record(record)
    assert not share['authoritative_current_market_cap_eligible']
    assert not share['research_proxy_eligible'] and share['value'] is None
    row = {'share_basis_input': share}
    context = _valuation(row)['official_share_observation']
    assert context['value'] == 7675465855 and not context['current_basis_eligible']
    assert _valuation_handoff(row)['official_share_observation'] == context


@pytest.mark.parametrize('lifecycle', ['PROPOSED', 'APPROVED', 'RECORD_DATE', 'LISTING', 'TRADING_ELIGIBILITY', None])
def test_calendar_and_resulting_quantity_do_not_invent_common_execution(lifecycle):
    result = reconcile_subsequent_events([{'event_type': 'STOCK_DIVIDEND', 'execution_date': '2026-07-02',
        'resulting_shares': 8442964520, 'lifecycle': lifecycle}], after_date='2025-12-31', session='2026-10-07')
    assert result['blockers'] and result['considered'][0]['disposition'] != 'EXECUTED_WITH_RESULTING_SHARES'
