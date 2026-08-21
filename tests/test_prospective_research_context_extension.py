import copy
import json
from pathlib import Path

import pytest

from prospective_research_context_extension import build, write_immutable
from prospective_research_learning import context_extension_dimensions
from run_prospective_research_context_extension import ROOT, SNAPSHOT, run


def _load(relative: str):
    return json.loads((ROOT / relative).read_text(encoding='utf8'))


def test_extension_is_immutable_t_state_and_preserves_source_identities(tmp_path: Path):
    original_bytes = SNAPSHOT.read_bytes()
    snapshot, first = run(); _, second = run()
    assert SNAPSHOT.read_bytes() == original_bytes
    assert snapshot['snapshot_id'] == 'prospective_research_snapshot:caa5136ad5787d4ae13ccc9d450e1312b55e6307a83042a24013a8e321b61c4a'
    assert first['extension_content_identity'] == second['extension_content_identity']
    assert first['research_session'] == '2026-08-20'
    assert first['coverage']['records'] == 523
    assert first['coverage']['setup_linkage_count'] == 523
    assert first['coverage']['market_context_linkage_count'] == 523
    assert first['coverage']['relative_authority_counts'] == {'QUALIFIED_CLASSIFICATION': 27, 'PROVIDER_DESCRIPTIVE_CLASSIFICATION': 486, 'UNAVAILABLE': 10}
    assert first['coverage']['cohort_key_member_counts']['setup:BREAKOUT_CONTEXT'] == 19
    assert first['coverage']['cohort_key_member_counts']['setup:TREND_CONTINUATION_CONTEXT'] == 193
    assert first['seal']['sealed_before_accepted_future_observation'] is True
    dimensions = context_extension_dimensions(snapshot, first)
    assert dimensions['outcome_status'] == 'PENDING_FUTURE_OBSERVATION'
    assert len(dimensions['dimensions']) == 523
    mixed_session = copy.deepcopy(first); mixed_session['records'][0]['research_session'] = '2026-08-21'
    with pytest.raises(ValueError, match='PROSPECTIVE_CONTEXT_EXTENSION_SESSION_MISMATCH'):
        context_extension_dimensions(snapshot, mixed_session)
    extension_path = tmp_path / 'extension.json'; write_immutable(extension_path, first); write_immutable(extension_path, first)
    changed = dict(first); changed['research_session'] = '2026-08-21'
    with pytest.raises(ValueError): write_immutable(extension_path, changed)


def test_extension_rejects_later_source_session_and_preserves_setup_identity():
    snapshot, extension = run()
    setup = _load('operations-review/research-setup-classification-v1-20260820/research_setup_classification_artifact.json')
    first_setup = setup['records'][0]['setup_evaluations'][0]['setup_content_identity']
    assert first_setup in {item['setup_content_identity'] for item in extension['records'][0]['setup']['evaluations']}
    later_setup = copy.deepcopy(setup); later_setup['research_session'] = '2026-08-21'
    with pytest.raises(ValueError, match='TEMPORAL_SOURCE_SESSION_MISMATCH:setup'):
        build(snapshot, later_setup,
              _load('operations-review/price-structure-breakout-context-v1-20260820/price_structure_breakout_context_artifact.json'),
              _load('operations-review/market-regime-breadth-context-v1-20260820/market_regime_breadth_context_artifact.json'),
              _load('operations-review/downside-uncertainty-research-context-v1-20260820/downside_uncertainty_research_context_artifact.json'),
              _load('operations-review/sector-relative-research-context-v1-20260820/sector_relative_research_context_artifact.json'))
