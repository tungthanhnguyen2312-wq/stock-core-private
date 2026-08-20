from run_catalyst_event_research_context import run


def test_retained_event_context_is_deterministic_and_preserves_event_fact_boundaries():
    first, overlay = run(); second, _ = run()
    assert first['artifact_identity'] == second['artifact_identity']
    assert first['coverage']['cohort_records'] == 523
    assert first['coverage']['event_covered_records'] == 1
    assert first['coverage']['no_event_evidence_records'] == 522
    event = first['event_facts'][0]
    assert event['ticker'] == 'HPG'
    assert event['event_fact_classification'] == 'FACT'
    assert event['temporal_state'] == 'COMPLETED'
    assert event['unknown_dates'] == {'ex_date': True, 'record_date': True}
    assert event['authority_tier'] == 'OFFICIAL_QUALIFIED'
    assert event['evidence_identity']
    assert len({row['evidence_identity'] for row in first['event_facts']}) == len(first['event_facts'])
    hpg = next(row for row in first['records'] if row['ticker'] == 'HPG')
    assert hpg['catalyst_interpretations'][0]['classification'] == 'INFERENCE'
    assert hpg['catalyst_interpretations'][0]['event_evidence_identity'] == event['evidence_identity']
    assert hpg['catalyst_interpretations'][0]['expected_mechanism'] == 'UNKNOWN'
    assert all(not entry['events'] for entry in overlay['entries'])
