"""Focused tests for prospective research cohort diagnostics V1."""
from __future__ import annotations

import copy
import pytest

from prospective_research_cohort_diagnostics import (
    HORIZONS,
    MATURITY_NO_OBSERVATIONS,
    MATURITY_OBSERVED_IMMATURE_SAMPLE,
    MATURITY_PENDING_OUTCOMES,
    build_cohort_diagnostics,
)
from run_prospective_research_cohort_diagnostics import _load, run


def test_cohort_diagnostics_deterministic_and_replayable():
    first_artifact, first_summary = run()
    second_artifact, second_summary = run()
    assert first_artifact == second_artifact
    assert first_summary == second_summary
    assert first_artifact['schema_version'] == '1.0.0'
    assert first_artifact['contract_version'] == 'prospective_research_cohort_diagnostics/v1'
    assert first_artifact['disposition'] == 'PROSPECTIVE_RESEARCH_COHORT_DIAGNOSTICS_V1_READY'
    assert first_artifact['cohort_summary_count'] == 87


def test_input_ordering_invariance():
    ledger = _load('operations-review/prospective-daily-rollforward-v1-20260821/prospective_learning_ledger.json')
    first_attribution = _load('operations-review/first-real-prospective-attribution-v1-20260821/first_real_prospective_attribution_artifact.json')
    snap_20 = _load('operations-review/prospective-research-learning-v1-20260820/caa5136ad5787d4ae13ccc9d450e1312b55e6307a83042a24013a8e321b61c4a.json')
    snap_21 = _load('operations-review/prospective-daily-rollforward-v1-20260821/2026-08-21.snapshot.json')
    ext_20 = _load('operations-review/prospective-research-context-extension-v1-successor-20260820/6cc76efaaf55b4262b6d94d53abda75dc1a0289d17c7d195014e11a07e987807.json')

    # Reorder snapshots
    diag_ordered = build_cohort_diagnostics(
        ledger=ledger,
        attributions=[first_attribution],
        snapshots=[snap_20, snap_21],
        extensions=[ext_20],
    )
    diag_reversed = build_cohort_diagnostics(
        ledger=ledger,
        attributions=[first_attribution],
        snapshots=[snap_21, snap_20],
        extensions=[ext_20],
    )
    assert diag_ordered == diag_reversed


def test_exact_observed_pending_missing_counts():
    artifact, _ = run()
    hn = artifact['data_accumulation_needs']['horizon_needs']
    
    # H1 counts
    assert hn['H1']['total_observations'] == 1047
    assert hn['H1']['observed_count'] == 521
    assert hn['H1']['missing_count'] == 2
    assert hn['H1']['pending_count'] == 524
    assert hn['H1']['observed_sessions'] == ['2026-08-20']
    assert hn['H1']['pending_sessions'] == ['2026-08-21']

    # H3 & H5 counts
    for h in ('H3', 'H5'):
        assert hn[h]['total_observations'] == 1047
        assert hn[h]['observed_count'] == 0
        assert hn[h]['missing_count'] == 0
        assert hn[h]['pending_count'] == 1047
        assert hn[h]['status'] == 'ALL_OUTCOMES_PENDING'


def test_no_missing_as_zero_behavior():
    artifact, _ = run()
    overall_h1 = [
        c for c in artifact['cohort_diagnostics']
        if c['cohort_dimension'] == 'overall' and c['research_horizon'] == 'H1'
    ][0]
    
    # Missing count is 2 (BRS, CCS), observed is 521.
    assert overall_h1['unavailable_missing_count'] == 2
    assert overall_h1['observed_outcome_count'] == 521
    
    # Descriptive statistics count must match observed_outcome_count (521), NOT 523 or 1047
    stats = overall_h1['descriptive_statistics']
    assert stats['count'] == 521
    
    # The sum of positive + negative + zero must equal 521 exactly
    assert stats['positive_count'] + stats['negative_count'] + stats['zero_count'] == 521
    assert stats['positive_count'] == 350
    assert stats['negative_count'] == 91
    assert stats['zero_count'] == 80


def test_strict_temporal_safety_rejects_future_not_strictly_later():
    ledger = _load('operations-review/prospective-daily-rollforward-v1-20260821/prospective_learning_ledger.json')
    first_attribution = _load('operations-review/first-real-prospective-attribution-v1-20260821/first_real_prospective_attribution_artifact.json')
    snap_20 = _load('operations-review/prospective-research-learning-v1-20260820/caa5136ad5787d4ae13ccc9d450e1312b55e6307a83042a24013a8e321b61c4a.json')
    snap_21 = _load('operations-review/prospective-daily-rollforward-v1-20260821/2026-08-21.snapshot.json')
    ext_20 = _load('operations-review/prospective-research-context-extension-v1-successor-20260820/6cc76efaaf55b4262b6d94d53abda75dc1a0289d17c7d195014e11a07e987807.json')

    # Mutate attribution precondition to violate T < outcome_session
    corrupted_attr = copy.deepcopy(first_attribution)
    corrupted_attr['precondition']['future_session'] = '2026-08-20'
    corrupted_attr = dict(corrupted_attr)
    import hashlib, json
    body = dict(corrupted_attr)
    body.pop('artifact_identity', None)
    corrupted_attr['artifact_identity'] = 'first_real_prospective_attribution:' + hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    ).hexdigest()

    corrupted_ledger = copy.deepcopy(ledger)
    corrupted_ledger['rows'][0]['horizons']['H1']['attribution_identity'] = corrupted_attr['artifact_identity']
    body_l = dict(corrupted_ledger)
    body_l.pop('ledger_identity', None)
    corrupted_ledger['ledger_identity'] = 'prospective_learning_ledger:' + hashlib.sha256(
        json.dumps(body_l, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    ).hexdigest()

    with pytest.raises(ValueError, match='TEMPORAL_SAFETY_VIOLATION_FUTURE_NOT_STRICTLY_LATER'):
        build_cohort_diagnostics(
            ledger=corrupted_ledger,
            attributions=[corrupted_attr],
            snapshots=[snap_20, snap_21],
            extensions=[ext_20],
        )


def test_sample_maturity_states():
    artifact, _ = run()
    for c in artifact['cohort_diagnostics']:
        if c['research_horizon'] in ('H3', 'H5'):
            assert c['sample_maturity_state'] == MATURITY_PENDING_OUTCOMES
            assert c['descriptive_statistics'] is None
        elif c['research_horizon'] == 'H1':
            assert c['sample_maturity_state'] == MATURITY_OBSERVED_IMMATURE_SAMPLE
            assert c['observed_sessions_count'] == 1
            assert c['descriptive_statistics'] is not None


def test_no_authority_escalation():
    artifact, _ = run()
    forbidden_keys = {
        'alpha', 'sharpe', 'information_ratio', 'p_value', 'p_values',
        'statistical_significance', 'expected_return', 'calibrated_probability',
        'hit_rate', 'causal_effect', 'predictive_power', 'recommendation',
        'target_price', 'optimal_weight',
    }
    
    # Check top-level and cohort-level payloads
    assert not (set(artifact.keys()) & forbidden_keys)
    for c in artifact['cohort_diagnostics']:
        assert not (set(c.keys()) & forbidden_keys)
        if c['descriptive_statistics']:
            assert not (set(c['descriptive_statistics'].keys()) & forbidden_keys)


def test_missing_observations_reconciliation():
    artifact, _ = run()
    missing = artifact['data_accumulation_needs']['missing_observation_concentration']
    assert len(missing) == 2
    missing_tickers = {m['ticker'] for m in missing}
    assert missing_tickers == {'BRS', 'CCS'}
    for m in missing:
        assert m['missing_state_reason'] == 'FUTURE_SESSION_MISSING'
        assert m['t_session'] == '2026-08-20'
        assert m['future_session'] == '2026-08-21'
