from run_downside_uncertainty_research_context import run, write_immutable
import pytest


def test_downside_vector_is_deterministic_and_preserves_unknowns():
    v1, first, overlay = run(); repeat_v1, second, _ = run()
    assert v1['artifact_identity'] == repeat_v1['artifact_identity']; assert first['artifact_identity'] == second['artifact_identity']
    assert v1['contract_version'].endswith('/v1'); assert first['contract_version'].endswith('/v2')
    assert v1['coverage']['core_observed_adverse_technical_count'] == 378; assert first['coverage']['core_observed_adverse_technical_count'] == 378
    assert first['coverage']['records'] == 523
    assert len(overlay['entries']) == 25
    assert v1['source_artifact_identities']['price_structure'] is None
    assert 'PRICE_STRUCTURE_DOWNSIDE_CONTEXT' not in v1['records'][0]['domains']
    v1_adverse = {row['ticker'] for row in v1['records'] if row['domains']['TECHNICAL_DOWNSIDE_CONTEXT']['status'] == 'OBSERVED_ADVERSE_TECHNICAL_CONTEXT'}
    v2_adverse = {row['ticker'] for row in first['records'] if row['domains']['TECHNICAL_DOWNSIDE_CONTEXT']['status'] == 'OBSERVED_ADVERSE_TECHNICAL_CONTEXT'}
    assert v1_adverse == v2_adverse
    for ticker in ('AAN', 'MIG', 'TCW', 'TRA'):
        row = next(row for row in first['records'] if row['ticker'] == ticker)
        assert ticker not in v1_adverse
        assert row['domains']['PRICE_STRUCTURE_DOWNSIDE_CONTEXT']['reason_codes'] == ['NEAR_RECENT_SUPPORT_PRICE_STRUCTURE_CONTEXT']
    for row in first['records']:
        domains = row['domains']
        assert domains['EXECUTION_RISK_STATUS']['status'] == 'EXECUTION_RISK_NOT_ASSESSABLE'
        assert domains['PRICE_STRUCTURE_DOWNSIDE_CONTEXT']['status'] in {'PRICE_STRUCTURE_DOWNSIDE_CONTEXT_PRESENT', 'NO_PRICE_STRUCTURE_DOWNSIDE_CONTEXT'}
        assert domains['EVENT_VISIBILITY']['status'] in {'NO_RETAINED_EVENT_EVIDENCE', 'EVIDENCED_EVENT_CONTEXT'}
        assert domains['EVIDENCE_UNCERTAINTY']['status'].startswith('EVIDENCE_UNCERTAINTY_')
    assert first['authority_boundary']['evidence_uncertainty_not_economic_risk']
    assert first['authority_boundary']['event_absence_not_no_event_risk']


def test_versioned_downside_artifacts_are_immutable(tmp_path):
    v1, v2, _ = run(); path = tmp_path / 'v1.json'
    write_immutable(path, v1); write_immutable(path, v1)
    with pytest.raises(ValueError, match='IMMUTABLE_DOWNSIDE_CONTEXT_CONTENT_CONFLICT'):
        write_immutable(path, v2)
