import copy
import json
from pathlib import Path

import pytest

from prospective_research_learning import (
    ENTRY_RELEVANT_COHORT_STATES,
    freeze_prospective_research_cohort,
    replay_prospective_research_cohort_snapshot,
    resolve_entry_relevant_cohort,
    write_immutable,
)
from tools.run_prospective_research_cohort_collection import output_path, resolve

ROOT = Path(__file__).resolve().parents[1]
SESSION = '2026-08-25'
PACKET_PATH = ROOT / 'operations-review/current-research-decision-packet-v1-20260825/current_research_decision_packet_artifact.json'
HPG_VCB_HISTORICAL = ROOT / 'operations-review/current-decision-prospective-learning-v1-20260824/current_decision_prospective_snapshot_20260821.json'
LEGACY_MANIFEST = ROOT / 'operations-review/prospective-research-case-operations-v1-20260822/operating_manifest.json'


def _triage():
    path = ROOT / 'operations-review/full-universe-entry-candidate-triage-v1-20260825/full_universe_entry_candidate_triage_20260825.json'
    return json.loads(path.read_text(encoding='utf-8'))


def _packet():
    return json.loads(PACKET_PATH.read_text(encoding='utf-8'))


def test_real_2026_08_25_cohort_matches_governed_triage_counts_not_hpg_vcb():
    triage = _triage()
    cohort = resolve_entry_relevant_cohort(triage)
    assert len(cohort) == 95
    assert sum(v['admission_state'] == 'BASE_BUILDING' for v in cohort.values()) == 17
    assert sum(v['admission_state'] == 'BREAKOUT_READY' for v in cohort.values()) == 14
    assert sum(v['admission_state'] == 'EARLY_REVERSAL_CANDIDATE' for v in cohort.values()) == 64
    assert sum(v['high_priority_review_eligible'] for v in cohort.values()) == 91
    # The cohort is derived purely from today's triage evidence, not carried forward from the
    # original HPG/VCB pilot -- neither is currently in an entry-relevant tactical state.
    assert 'HPG' not in cohort
    assert 'VCB' not in cohort


def test_freeze_is_deterministic_and_replay_accepts_it():
    triage, packet = _triage(), _packet()
    first = freeze_prospective_research_cohort(session=SESSION, triage=triage, decision_packet=packet)
    second = freeze_prospective_research_cohort(session=SESSION, triage=triage, decision_packet=packet)
    assert first['snapshot_id'] == second['snapshot_id']
    replay_prospective_research_cohort_snapshot(first)
    assert first['cohort_count'] == 95
    assert first['decision_packet_coverage'] == {'available': 95, 'unavailable_or_malformed': 0}
    assert first['future_outcomes'] == 'PENDING_FUTURE_OBSERVATION'


def test_freeze_without_decision_packet_still_succeeds_degraded():
    triage = _triage()
    snapshot = freeze_prospective_research_cohort(session=SESSION, triage=triage, decision_packet=None)
    replay_prospective_research_cohort_snapshot(snapshot)
    assert snapshot['cohort_count'] == 95
    assert snapshot['decision_packet_coverage'] == {'available': 0, 'unavailable_or_malformed': 95}
    assert all(row['decision_packet_status'] == 'UNAVAILABLE_NOT_IN_PACKET' for row in snapshot['frozen_records'])
    assert all(row['current_decision_context'] == {} for row in snapshot['frozen_records'])


def test_tampering_packet_without_recomputing_identity_fails_closed_at_whole_file_level():
    triage, packet = _triage(), copy.deepcopy(_packet())
    any_ticker = next(iter(resolve_entry_relevant_cohort(triage)))
    packet['records'][any_ticker]['components'] = 'THIS_SHOULD_BE_A_MAPPING_NOT_A_STRING'
    with pytest.raises(Exception):
        # A whole-file-level corruption of an already-hashed packet fails closed at replay --
        # confirming freeze_prospective_research_cohort does not silently trust a tampered packet.
        freeze_prospective_research_cohort(session=SESSION, triage=triage, decision_packet=packet)


def test_malformed_single_record_isolated_when_packet_hash_is_recomputed():
    # Simulate "one malformed ticker" without re-triggering the whole-packet hash guard: rebuild
    # the packet's own identity over the corrupted payload, so only structural-shape validation
    # inside freeze_prospective_research_cohort is exercised (not the packet's own tamper gate).
    from current_research_decision_packet import content_identity
    triage, packet = _triage(), copy.deepcopy(_packet())
    any_ticker = next(iter(resolve_entry_relevant_cohort(triage)))
    packet['records'][any_ticker]['components'] = 'MALFORMED'
    packet.update(content_identity(packet))
    snapshot = freeze_prospective_research_cohort(session=SESSION, triage=triage, decision_packet=packet)
    replay_prospective_research_cohort_snapshot(snapshot)
    rows = {row['ticker']: row for row in snapshot['frozen_records']}
    assert rows[any_ticker]['decision_packet_status'] == 'MALFORMED'
    other_tickers = [t for t in rows if t != any_ticker]
    assert any(rows[t]['decision_packet_status'] not in ('MALFORMED', 'UNAVAILABLE_NOT_IN_PACKET') for t in other_tickers)
    assert snapshot['cohort_count'] == 95


def test_session_mismatch_and_tamper_fail_closed():
    triage, packet = _triage(), _packet()
    with pytest.raises(ValueError, match='SESSION_MISMATCH'):
        freeze_prospective_research_cohort(session='2026-08-24', triage=triage, decision_packet=packet)
    snapshot = freeze_prospective_research_cohort(session=SESSION, triage=triage, decision_packet=packet)
    tampered = copy.deepcopy(snapshot)
    tampered['cohort_count'] = 1
    with pytest.raises(ValueError, match='IDENTITY_MISMATCH'):
        replay_prospective_research_cohort_snapshot(tampered)


def test_no_future_outcome_or_scoring_fields_can_survive_replay():
    triage, packet = _triage(), _packet()
    snapshot = freeze_prospective_research_cohort(session=SESSION, triage=triage, decision_packet=packet)
    injected = copy.deepcopy(snapshot)
    injected['frozen_records'][0]['current_decision_context']['recommendation'] = 'BUY'
    injected['snapshot_id'] = 'prospective_research_cohort_snapshot:' + __import__('hashlib').sha256(
        json.dumps({k: v for k, v in injected.items() if k != 'snapshot_id'}, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    ).hexdigest()
    with pytest.raises(ValueError, match='HINDSIGHT_OR_SCORING_FIELD_PRESENT'):
        replay_prospective_research_cohort_snapshot(injected)


def test_immutable_write_conflicts_on_mutation_and_is_idempotent_on_identical_content(tmp_path):
    triage, packet = _triage(), _packet()
    snapshot = freeze_prospective_research_cohort(session=SESSION, triage=triage, decision_packet=packet)
    path = tmp_path / 'snapshot.json'
    write_immutable(path, snapshot)
    write_immutable(path, snapshot)  # identical content is a no-op, not a conflict
    conflicting = copy.deepcopy(snapshot)
    conflicting['high_priority_review_eligible_count'] = 0
    with pytest.raises(ValueError, match='IMMUTABLE_SNAPSHOT_CONTENT_CONFLICT'):
        write_immutable(path, conflicting)


def test_cli_resolve_reproduces_real_session_and_output_path_is_session_bound():
    result = resolve(SESSION, decision_packet_path=PACKET_PATH)
    snapshot = result['snapshot']
    assert snapshot['cohort_count'] == 95
    assert output_path(snapshot).name == 'prospective_research_cohort_snapshot_2026-08-25.json'
    assert output_path(snapshot).parent.name == 'prospective-research-cohort-collection-v1'


def test_cli_resolve_rejects_unregistered_or_ungoverned_session():
    with pytest.raises(ValueError, match='SESSION_NOT_GOVERNED_COMPLETED'):
        resolve('2026-08-22')
    with pytest.raises(ValueError, match='SESSION_NOT_GOVERNED_COMPLETED'):
        resolve('2026-08-27')


def test_old_hpg_vcb_and_five_ticker_pilot_artifacts_are_byte_unchanged():
    # These predate this milestone and must never be rewritten by the new cohort collector.
    before_snapshot = HPG_VCB_HISTORICAL.read_bytes()
    before_manifest = LEGACY_MANIFEST.read_bytes()
    resolve(SESSION, decision_packet_path=PACKET_PATH)
    assert HPG_VCB_HISTORICAL.read_bytes() == before_snapshot
    assert LEGACY_MANIFEST.read_bytes() == before_manifest
    assert json.loads(before_snapshot)['snapshot_id'] == 'prospective_research_snapshot:d227f98bfc0f9d79ae20ae0d686d2eab8085ecb014da3bf48345de7db3c3daf1'
