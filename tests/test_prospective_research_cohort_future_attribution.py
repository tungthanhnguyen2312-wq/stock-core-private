import copy
import json
from pathlib import Path

import pytest

from field_temporal_contract import stable_id
from prospective_research_learning import (
    ENTRY_RELEVANT_COHORT_STATES,
    OBSERVED_CHANGE_SEMANTICS,
    attribute_prospective_research_cohort_first_future,
    first_real_observation,
    freeze_prospective_research_cohort,
    replay_prospective_research_cohort_future_attribution,
    replay_prospective_research_cohort_snapshot,
    write_immutable,
)
from tools.run_prospective_research_cohort_attribution import (
    output_path,
    resolve_exact_session_bundle,
)

ROOT = Path(__file__).resolve().parents[1]
T_SESSION = '2026-08-25'
FUTURE_SESSION = '2026-08-26'
PRICE_BASIS = 'CURRENT_DESCRIPTIVE_DNSE_REST_ADJUSTED_RETROSPECTIVE_RAW_AS_TRADED_NOT_PROMOTED'
FORBIDDEN = (
    'win_rate', 'hit_rate', 'expected_return', 'probability', 'score',
    'recommendation', 'target_price', 'position_size',
)


def _seal_snapshot(payload: dict) -> dict:
    body = dict(payload)
    body.pop('snapshot_sha256', None)
    body.pop('snapshot_identity', None)
    digest = stable_id(body)
    payload['snapshot_sha256'] = digest
    payload['snapshot_identity'] = 'p3f9_exact_session_snapshot:' + digest
    return payload


def _seal_scaleout(payload: dict, snapshot_identity: str, session: str) -> dict:
    payload.setdefault('schema_version', '1.0.0')
    payload['contract_version'] = 'p3f9b_market_wide_exact_session_scaleout/v1'
    payload['snapshot_identity'] = snapshot_identity
    payload['resolved_session'] = {
        'resolved_completed_session': session,
        'retained_snapshot_session': session,
        'mva_bundle_session': session,
        'exact_session_equality': True,
        'incomplete_intraday_used': False,
    }
    payload['authority_boundary'] = {
        'CURRENT_MARKET': 'DESCRIPTIVE_QUALIFIED_ONLY',
        'RAW_AS_TRADED': 'NOT_PROMOTED',
        'HISTORICAL_PIT': 'BLOCKED',
    }
    body = dict(payload)
    body.pop('artifact_sha256', None)
    body.pop('artifact_identity', None)
    digest = stable_id(body)
    payload['artifact_sha256'] = digest
    payload['artifact_identity'] = 'p3f9b_market_wide_exact_session_scaleout:' + digest
    return payload


def _observation(session: str, close, *, representation=None, basis=None, transform=None):
    return {
        'session': session,
        'open': close, 'high': close, 'low': close, 'close': close, 'volume': 1,
        'provider': 'DNSE', 'dataset': 'DNSE_OHLC_1D',
        'field_identity': {'close': 'DNSE_OHLC.close'},
        'field_representation': {
            'open': 'DNSE_PROVIDER_NATIVE_RAW',
            'high': 'DNSE_PROVIDER_NATIVE_RAW',
            'low': 'DNSE_PROVIDER_NATIVE_RAW',
            'close': representation or 'DNSE_PROVIDER_NATIVE_RAW',
        },
        'transformation_identity': transform or 'identity_provider_numeric_ohlc/v1',
        'price_unit': 'SOURCE_PRICE_UNIT_UNDOCUMENTED',
        'price_basis': basis or PRICE_BASIS,
        'qualification': 'CURRENT_MARKET_DESCRIPTIVE_QUALIFIED_ONLY',
    }


def _record(session: str, close, *, disposition='EXACT_SESSION_RETAINED', extra=None, **obs_kw):
    observations = list(extra or [])
    if close is not None:
        observations.append(_observation(session, close, **obs_kw))
    return {
        'disposition': disposition,
        'status': 'OBSERVED' if disposition == 'EXACT_SESSION_RETAINED' else disposition,
        'observations': observations,
    }


def _exact_pair(session: str, records: dict) -> tuple[dict, dict]:
    snapshot = _seal_snapshot({
        'schema_version': '1.0.0',
        'contract_version': 'p3f9_exact_session_mva_snapshot/v2',
        'resolved_completed_session': session,
        'retained_snapshot_session': session,
        'records': records,
        'authority_boundary': {
            'CURRENT_MARKET': 'DESCRIPTIVE_QUALIFIED_ONLY',
            'RAW_AS_TRADED': 'NOT_PROMOTED',
            'HISTORICAL_PIT': 'BLOCKED',
        },
    })
    scaleout = _seal_scaleout({}, snapshot['snapshot_identity'], session)
    return snapshot, scaleout


def _triage(members):
    buckets = {state: [] for state in ENTRY_RELEVANT_COHORT_STATES}
    for ticker, state, high_priority in members:
        buckets[state].append({'ticker': ticker, 'high_priority_review_eligible': high_priority})
    return {
        'source_market_session': T_SESSION,
        'artifact_identity': 'full_universe_entry_candidate_triage:fixture',
        'all_entry_relevant_records': buckets,
    }


def _world(*, extra_t=None, extra_future=None, members=None):
    members = members or [
        ('AAA', 'BASE_BUILDING', True),
        ('BBB', 'BREAKOUT_READY', True),
        ('CCC', 'EARLY_REVERSAL_CANDIDATE', True),
        ('DDD', 'EARLY_REVERSAL_CANDIDATE', False),
        ('EEE', 'EARLY_REVERSAL_CANDIDATE', True),
        ('FFF', 'BASE_BUILDING', False),
    ]
    snapshot = freeze_prospective_research_cohort(session=T_SESSION, triage=_triage(members))
    replay_prospective_research_cohort_snapshot(snapshot)
    t_records = {
        'AAA': _record(T_SESSION, 100),
        'BBB': _record(T_SESSION, 200),
        'CCC': _record(T_SESSION, 50),
        'DDD': _record(T_SESSION, 40),
        'EEE': _record(T_SESSION, None, disposition='SESSION_MISSING',
                       extra=[_observation('2026-08-24', 99)]),
        'FFF': _record(T_SESSION, 0),
    }
    if extra_t:
        t_records.update(extra_t)
    future_records = {
        'AAA': _record(FUTURE_SESSION, 110),
        'BBB': _record(FUTURE_SESSION, 180),
        'CCC': _record(FUTURE_SESSION, 50),
        'DDD': _record(FUTURE_SESSION, None, disposition='SESSION_MISSING',
                       extra=[_observation(T_SESSION, 41)]),
        'EEE': _record(FUTURE_SESSION, 60),
        'FFF': _record(FUTURE_SESSION, 1),
        'ZZZ': _record(FUTURE_SESSION, 999),
    }
    if extra_future:
        future_records.update(extra_future)
    t_snap, t_scale = _exact_pair(T_SESSION, t_records)
    future_snap, future_scale = _exact_pair(FUTURE_SESSION, future_records)
    return snapshot, t_snap, t_scale, future_snap, future_scale


def _attribute(**kwargs):
    snapshot, t_snap, t_scale, future_snap, future_scale = _world()
    return attribute_prospective_research_cohort_first_future(
        snapshot=snapshot, t_exact_snapshot=t_snap, t_exact_scaleout=t_scale,
        future_exact_snapshot=future_snap, future_exact_scaleout=future_scale,
        future_session=FUTURE_SESSION, **kwargs)


def test_future_session_must_be_strictly_later():
    snapshot, t_snap, t_scale, future_snap, future_scale = _world()
    with pytest.raises(ValueError, match='FUTURE_SESSION_NOT_STRICTLY_LATER'):
        attribute_prospective_research_cohort_first_future(
            snapshot=snapshot, t_exact_snapshot=t_snap, t_exact_scaleout=t_scale,
            future_exact_snapshot=future_snap, future_exact_scaleout=future_scale,
            future_session=T_SESSION)
    with pytest.raises(ValueError, match='FUTURE_SESSION_NOT_STRICTLY_LATER'):
        attribute_prospective_research_cohort_first_future(
            snapshot=snapshot, t_exact_snapshot=t_snap, t_exact_scaleout=t_scale,
            future_exact_snapshot=future_snap, future_exact_scaleout=future_scale,
            future_session='2026-08-24')


def test_frozen_cohort_remains_exactly_t_cohort_and_future_only_ticker_excluded():
    artifact = _attribute()
    replay_prospective_research_cohort_future_attribution(artifact)
    tickers = [row['ticker'] for row in artifact['outcomes']]
    assert tickers == ['AAA', 'BBB', 'CCC', 'DDD', 'EEE', 'FFF']
    assert artifact['frozen_cohort_count'] == 6
    assert 'ZZZ' not in tickers
    assert artifact['cohort_reconciliation']['future_only_members_not_added_to_t'] == ['ZZZ']


def test_missing_future_and_missing_t_remain_explicit_rows():
    rows = {row['ticker']: row for row in _attribute()['outcomes']}
    assert rows['DDD']['outcome_status'] == 'MISSING_FUTURE_EXACT_OBSERVATION'
    assert 'observed_return' not in rows['DDD']
    assert rows['EEE']['outcome_status'] == 'MISSING_T_EXACT_OBSERVATION'
    assert 'observed_return' not in rows['EEE']
    assert rows['EEE'].get('t_close') is None


def test_stale_prior_session_future_value_cannot_substitute():
    rows = {row['ticker']: row for row in _attribute()['outcomes']}
    assert rows['DDD']['outcome_status'] == 'MISSING_FUTURE_EXACT_OBSERVATION'
    assert rows['DDD']['missing_state_reason'] == 'FUTURE_SESSION_MISSING'
    assert rows['DDD'].get('future_close') is None


def test_exact_t_and_future_close_compute_descriptive_change_and_return():
    row = {r['ticker']: r for r in _attribute()['outcomes']}['AAA']
    assert row['outcome_status'] == 'OBSERVED_EXACT_FUTURE_SESSION'
    assert row['t_close'] == 100
    assert row['future_close'] == 110
    assert row['observed_price_change'] == 10
    assert row['observed_return'] == pytest.approx(0.1)
    assert row['direction'] == 'POSITIVE'
    assert row['observed_change_semantics'] == OBSERVED_CHANGE_SEMANTICS


def test_zero_t_close_fails_safely_without_dropping_row():
    row = {r['ticker']: r for r in _attribute()['outcomes']}['FFF']
    assert row['outcome_status'] == 'T_CLOSE_INVALID_OR_ZERO'
    assert 'observed_return' not in row
    assert row['ticker'] == 'FFF'


def test_price_representation_preserved_and_raw_as_traded_not_promoted():
    artifact = _attribute()
    observed = [row for row in artifact['outcomes'] if row['outcome_status'] == 'OBSERVED_EXACT_FUTURE_SESSION']
    assert observed
    for row in observed:
        assert row['t_price_representation']['close_field_representation'] == 'DNSE_PROVIDER_NATIVE_RAW'
        assert row['future_price_representation']['close_field_representation'] == 'DNSE_PROVIDER_NATIVE_RAW'
        assert row['t_price_representation']['price_basis'] == PRICE_BASIS
        assert 'RAW_AS_TRADED' not in row['t_price_representation']['price_basis'] or 'NOT_PROMOTED' in row['t_price_representation']['price_basis']
    assert artifact['price_representation']['raw_as_traded'] == 'NOT_PROMOTED'
    assert artifact['temporal_safety']['historical_raw_as_traded_or_pit_promoted'] is False


def test_mismatched_representation_is_unavailable_not_forced():
    snapshot, t_snap, t_scale, future_snap, future_scale = _world()
    future_snap['records']['AAA'] = _record(FUTURE_SESSION, 110, representation='SOMETHING_ELSE')
    future_snap, future_scale = _exact_pair(FUTURE_SESSION, future_snap['records'])
    artifact = attribute_prospective_research_cohort_first_future(
        snapshot=snapshot, t_exact_snapshot=t_snap, t_exact_scaleout=t_scale,
        future_exact_snapshot=future_snap, future_exact_scaleout=future_scale,
        future_session=FUTURE_SESSION)
    row = {r['ticker']: r for r in artifact['outcomes']}['AAA']
    assert row['outcome_status'] == 'PRICE_REPRESENTATION_COMPARISON_UNSAFE'
    assert 'observed_return' not in row


def test_group_summaries_for_three_frozen_triage_states():
    artifact = _attribute()
    groups = {item['group']: item for item in artifact['frozen_triage_state_summaries']}
    assert set(groups) == set(ENTRY_RELEVANT_COHORT_STATES)
    base = groups['BASE_BUILDING']
    assert base['frozen_count'] == 2
    assert base['observed_count'] == 1
    assert base['missing_count'] == 1
    assert base['positive'] == 1
    assert base['negative'] == 0
    assert base['unchanged'] == 0
    assert base['mean_observed_return'] == pytest.approx(0.1)
    assert base['median_observed_return'] == pytest.approx(0.1)
    brk = groups['BREAKOUT_READY']
    assert brk['frozen_count'] == 1
    assert brk['observed_count'] == 1
    assert brk['missing_count'] == 0
    assert brk['negative'] == 1
    assert brk['mean_observed_return'] == pytest.approx(-0.1)
    early = groups['EARLY_REVERSAL_CANDIDATE']
    assert early['frozen_count'] == 3
    assert early['observed_count'] == 1
    assert early['missing_count'] == 2
    assert early['unchanged'] == 1
    assert early['mean_observed_return'] == pytest.approx(0.0)


def test_group_frozen_counts_and_coverage_reconcile():
    artifact = _attribute()
    overall = artifact['overall']
    groups = artifact['frozen_triage_state_summaries']
    assert sum(item['frozen_count'] for item in groups) == overall['frozen_count'] == 6
    assert overall['observed_count'] + overall['missing_count'] == overall['frozen_count']
    assert overall['positive'] + overall['negative'] + overall['unchanged'] == overall['observed_count']
    for item in groups:
        assert item['observed_count'] + item['missing_count'] == item['frozen_count']
        assert item['positive'] + item['negative'] + item['unchanged'] == item['observed_count']
    assert overall['positive'] == 1
    assert overall['negative'] == 1
    assert overall['unchanged'] == 1
    assert overall['mean_observed_return'] == pytest.approx(0.0)
    assert overall['median_observed_return'] == pytest.approx(0.0)


def test_future_state_does_not_affect_t_membership():
    future_triage = {
        'artifact_identity': 'full_universe_entry_candidate_triage:future',
        'all_entry_relevant_records': {
            'BASE_BUILDING': [{'ticker': 'ZZZ', 'high_priority_review_eligible': True}],
            'BREAKOUT_READY': [],
            'EARLY_REVERSAL_CANDIDATE': [],
        },
    }
    future_tactical = {
        'artifact_identity': 'watchlist_tactical_entry_classifier:future',
        'records': {
            'AAA': {'entry_state': 'DOWNTREND', 'entry_action': 'AVOID'},
            'ZZZ': {'entry_state': 'BREAKOUT_READY', 'entry_action': 'BUY_ON_CONFIRMATION'},
        },
    }
    artifact = _attribute(future_triage=future_triage, future_tactical=future_tactical)
    tickers = [row['ticker'] for row in artifact['outcomes']]
    assert tickers == ['AAA', 'BBB', 'CCC', 'DDD', 'EEE', 'FFF']
    assert 'ZZZ' not in tickers
    aaa = {row['ticker']: row for row in artifact['outcomes']}['AAA']
    assert aaa['frozen_triage_state'] == 'BASE_BUILDING'
    assert aaa['future_descriptive_state']['future_triage_state'] == 'NOT_IN_FUTURE_ENTRY_RELEVANT_COHORT'
    assert aaa['future_descriptive_state']['future_tactical_state'] == 'DOWNTREND'
    assert aaa['future_descriptive_state']['not_outcome_success_or_failure'] is True
    assert aaa['outcome_status'] == 'OBSERVED_EXACT_FUTURE_SESSION'


def test_no_forbidden_predictive_or_recommendation_fields():
    artifact = _attribute()
    blob = json.dumps(artifact)
    for name in FORBIDDEN:
        assert f'"{name}"' not in blob


def test_snapshot_identity_mismatch_fails_closed():
    snapshot, t_snap, t_scale, future_snap, future_scale = _world()
    snapshot['snapshot_id'] = 'prospective_research_cohort_snapshot:' + '0' * 64
    with pytest.raises(ValueError, match='IDENTITY_MISMATCH'):
        attribute_prospective_research_cohort_first_future(
            snapshot=snapshot, t_exact_snapshot=t_snap, t_exact_scaleout=t_scale,
            future_exact_snapshot=future_snap, future_exact_scaleout=future_scale,
            future_session=FUTURE_SESSION)


def test_t_and_future_exact_source_identity_mismatch_fail_closed():
    snapshot, t_snap, t_scale, future_snap, future_scale = _world()
    bad_t = copy.deepcopy(t_scale)
    bad_t['artifact_identity'] = 'p3f9b_market_wide_exact_session_scaleout:' + 'a' * 64
    with pytest.raises(ValueError, match='T_EXACT_SOURCE_IDENTITY_MISMATCH'):
        attribute_prospective_research_cohort_first_future(
            snapshot=snapshot, t_exact_snapshot=t_snap, t_exact_scaleout=bad_t,
            future_exact_snapshot=future_snap, future_exact_scaleout=future_scale,
            future_session=FUTURE_SESSION)
    bad_future = copy.deepcopy(future_scale)
    bad_future['artifact_sha256'] = 'b' * 64
    with pytest.raises(ValueError, match='FUTURE_EXACT_SOURCE_IDENTITY_MISMATCH'):
        attribute_prospective_research_cohort_first_future(
            snapshot=snapshot, t_exact_snapshot=t_snap, t_exact_scaleout=t_scale,
            future_exact_snapshot=future_snap, future_exact_scaleout=bad_future,
            future_session=FUTURE_SESSION)


def test_identical_replay_is_idempotent(tmp_path):
    first = _attribute()
    second = _attribute()
    assert first == second
    replay_prospective_research_cohort_future_attribution(first)
    path = tmp_path / 'attr.json'
    write_immutable(path, first)
    write_immutable(path, second)
    conflicting = copy.deepcopy(first)
    conflicting['overall'] = dict(conflicting['overall'])
    conflicting['overall']['observed_count'] = 0
    with pytest.raises(ValueError, match='IMMUTABLE_SNAPSHOT_CONTENT_CONFLICT'):
        write_immutable(path, conflicting)


def test_no_network_in_attribution_or_runner_source():
    sources = [
        ROOT / 'prospective_research_learning.py',
        ROOT / 'tools' / 'run_prospective_research_cohort_attribution.py',
    ]
    banned = ('urllib', 'requests', 'http.client', 'dnse_access', 'fetch_capability_raw', 'socket')
    for path in sources:
        text = path.read_text(encoding='utf-8')
        for token in banned:
            assert token not in text, f'{path.name} contains {token}'


def test_output_path_is_session_bound():
    artifact = _attribute()
    path = output_path(artifact)
    assert path.name == 'prospective_research_cohort_future_attribution_2026-08-25_to_2026-08-26.json'
    assert path.parent.name == 'prospective-research-cohort-future-attribution-v1'


def test_ambiguous_exact_session_copies_fail_closed(tmp_path):
    registry = {
        'contract_version': 'daily_research_session_input_registry/v1',
        'completed_sessions': {
            FUTURE_SESSION: {'status': 'COMPLETED_RETAINED_EVIDENCE', 'frozen_input_identities': {'x': 'y'}},
        },
        'sessions': {FUTURE_SESSION: {}},
    }
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config' / 'daily_research_session_input_registry.json').write_text(
        json.dumps(registry), encoding='utf-8')
    a = tmp_path / 'operations-review' / 'p3f9b-market-wide-exact-session-scaleout-20260826'
    b = (tmp_path / 'operations-review' / 'canonical-post-close-v1' / FUTURE_SESSION /
         'post-close-attempt-1' / 'operations-review' / 'p3f9b-market-wide-exact-session-scaleout-20260826')
    for directory, close in ((a, 1), (b, 2)):
        directory.mkdir(parents=True)
        snap, scale = _exact_pair(FUTURE_SESSION, {'AAA': _record(FUTURE_SESSION, close)})
        (directory / 'p3f9b_mva_exact_session_snapshot.json').write_text(json.dumps(snap), encoding='utf-8')
        (directory / 'p3f9b_market_wide_exact_session_scaleout_artifact.json').write_text(
            json.dumps(scale), encoding='utf-8')
    from daily_research_session_operations import load_registry
    loaded = load_registry(tmp_path)
    with pytest.raises(ValueError, match='AMBIGUOUS_EXACT_SESSION_SOURCE'):
        resolve_exact_session_bundle(FUTURE_SESSION, tmp_path, registry=loaded)


def test_historical_first_real_observation_is_untouched_sibling():
    assert first_real_observation.__doc__ is not None
    source = (ROOT / 'prospective_research_learning.py').read_text(encoding='utf-8')
    assert "required_future = {" in source
    assert 'len(frozen) != 523' in source
    assert 'prospective_research_learning/cohort_future_attribution/v1' in source


def test_authority_boundary_is_descriptive_only():
    artifact = _attribute()
    assert artifact['authority'] == 'PROSPECTIVE_DESCRIPTIVE_ATTRIBUTION_ONLY'
    assert artifact['authority_effect'] == 'NONE'
    assert 'NOT_HISTORICAL_PIT_BACKTEST' in artifact['authority_boundaries']
    assert 'NOT_CALIBRATED' in artifact['authority_boundaries']
    assert artifact['horizon']['kind'] == 'FIRST_STRICTLY_LATER_COMPLETED_SESSION'
    assert artifact['horizon']['later_sessions_not_materialized'] is True


REAL_ARTIFACT = ROOT / 'operations-review' / 'prospective-research-cohort-future-attribution-v1' / 'prospective_research_cohort_future_attribution_2026-08-25_to_2026-08-26.json'


def test_real_2026_08_25_to_26_materialized_artifact_reconciles():
    if not REAL_ARTIFACT.is_file():
        pytest.skip('real first-future attribution artifact is not materialized')
    artifact = json.loads(REAL_ARTIFACT.read_text(encoding='utf-8'))
    replay_prospective_research_cohort_future_attribution(artifact)
    assert artifact['frozen_snapshot_identity'] == (
        'prospective_research_cohort_snapshot:4af5724516b386a3eda67515c322f01856eb9cb96a30287d3fa2a805f506bfc3')
    assert artifact['t_session'] == '2026-08-25'
    assert artifact['future_session'] == '2026-08-26'
    assert artifact['frozen_cohort_count'] == 95
    assert artifact['frozen_state_counts'] == {
        'BASE_BUILDING': 17, 'BREAKOUT_READY': 14, 'EARLY_REVERSAL_CANDIDATE': 64,
    }
    overall = artifact['overall']
    assert overall['frozen_count'] == 95
    assert overall['observed_count'] + overall['missing_count'] == 95
    assert overall['positive'] + overall['negative'] + overall['unchanged'] == overall['observed_count']
    assert sum(item['frozen_count'] for item in artifact['frozen_triage_state_summaries']) == 95
    assert artifact['authority_effect'] == 'NONE'
    assert artifact['price_representation']['raw_as_traded'] == 'NOT_PROMOTED'
