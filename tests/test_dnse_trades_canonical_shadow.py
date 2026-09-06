from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import dnse_trades_canonical_shadow as shadow


def _raw_page(path: Path, payload: object) -> None:
    frame = pd.DataFrame([{
        "provider": "DNSE", "dataset": "trades_history", "instrument": "HPG",
        "observation_id": "a" * 64, "raw_payload_hash": shadow._sha256(payload),
        "raw_payload_json": json.dumps(payload), "provenance_json": json.dumps({"ingestion_run_id": "fixture"}),
    }])
    frame.to_parquet(path)


def test_known_failure_and_confirmed_empty_selection_are_preserved():
    failed = shadow._unit_selection({
        "session": "2026-08-11", "instrument": "HPG", "logical_status": "REMAINING_FAILED", "original_status": "failed",
        "repair": {"repair_outcome": "failed"},
    })
    empty = shadow._unit_selection({
        "session": "2026-08-11", "instrument": "SSI", "logical_status": "ORIGINAL_SUCCESS_EMPTY", "original_status": "success",
        "source_raw_file": "fixture.parquet", "source_observation_id": "obs", "original_records": 0,
    })
    assert failed["selected_attempt"] == shadow.REMAINING_FAILED
    assert failed["selected_raw_file"] is None
    assert empty["selected_attempt"] == "ORIGINAL_SUCCESS_EMPTY"
    assert empty["logical_status"] == shadow.ORIGINAL_SUCCESS_EMPTY


def test_materializer_preserves_board_and_lineage_and_is_idempotent(tmp_path: Path):
    raw = tmp_path / "raw"
    raw.mkdir()
    _raw_page(raw / "page.parquet", {"trades": [
        {"symbol": "HPG", "time": "2026-08-11 09:00:00", "matchPrice": 10, "matchQtty": 2, "boardId": "G1"},
        {"symbol": "HPG", "time": "2026-08-11 09:01:00", "matchPrice": 10, "matchQtty": 2, "boardId": "X9"},
        "malformed",
    ]})
    manifest = tmp_path / "cohort.json"
    manifest.write_text(json.dumps({"cohort_id": "fixture", "sessions": [{"session_date": "2026-08-11", "raw_dir": str(raw)}]}), encoding="utf-8")
    first = shadow.materialize_cohort(cohort_manifest_path=manifest, shadow_root=tmp_path / "shadow", workers=1)
    second = shadow.materialize_cohort(cohort_manifest_path=manifest, shadow_root=tmp_path / "shadow", workers=1)
    rows = pd.read_parquet(first["sessions"][0]["output_file"])
    assert first["aggregate"]["canonical_rows"] == 2
    assert first["aggregate"]["quarantined_records"] == 1
    assert list(rows["board_id"]) == ["G1", "X9"]
    assert bool(rows.iloc[1]["board_semantic_review_required"])
    assert rows.iloc[0]["raw_record_identity"] != rows.iloc[1]["raw_record_identity"]
    assert second["rerun_behavior"] == "SKIP_VERIFIED_MATERIALIZATION"
    assert shadow.CANONICAL_SCHEMA.names == list(rows.columns)
