import json
from pathlib import Path

import pytest

from corporate_action_events import classify_retained_document, extract_event_observation, extract_text
from tools.run_historical_raw_pit_real_factor_qualification import build_artifact


ROOT = Path(__file__).resolve().parents[1]
RETENTION = ROOT / "operations-review/historical-raw-pit-real-factor-chain-qualification-v1-20260930/official_document_retention"

if not (RETENTION / "official_document_acquisition_manifest.json").is_file():
    pytest.skip("real official document bodies remain in the governed ignored evidence root", allow_module_level=True)


def test_vbb_hnx_notice_extracts_explicit_ex_date_and_ratio_but_not_execution():
    manifest = json.loads((RETENTION / "official_document_acquisition_manifest.json").read_text(encoding="utf-8"))
    record = next(row for row in manifest["records"] if row["ticker"] == "VBB")
    payload = (RETENTION / record["relative_path"]).read_bytes()
    observation = extract_event_observation(classify_retained_document(record, payload), extract_text(payload, record["content_type"]))
    assert observation["ex_date"] == "2026-06-26"
    assert observation["record_date"] == "2026-06-29"
    assert observation["stock_ratio"] == 0.1
    assert observation["lifecycle_state"] == "record_date_confirmed"


def test_replay_is_fail_closed_and_does_not_promote_global_authority():
    artifact = build_artifact()
    assert artifact["authority_boundary"]["real_factor_chain_qualified_count"] == 0
    assert artifact["authority_boundary"]["pit_backtest_eligible"] is False
    assert artifact["authority_boundary"]["execution_replay_eligible"] is False
    assert artifact["authority_boundary"]["active_universe"] == "UNKNOWN"
    assert artifact["event_outcomes"]["VBB:2026-06-26:BONUS"]["knowledge_cutoff"]["knowledge_available_at"] == "2026-06-19T08:39:00+07:00"
