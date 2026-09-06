from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import dnse_trades_canonical_shadow as shadow


def _raw_page(path: Path, payload: object) -> None:
    frame = pd.DataFrame([{
        "provider": "DNSE", "dataset": "trades_history", "instrument": "HPG",
        "observation_id": "a" * 64, "raw_payload_hash": shadow._sha256(payload),
        "raw_payload_json": json.dumps(payload), "provenance_json": json.dumps({"ingestion_run_id": "fixture"}),
    }])
    frame.to_parquet(path)


def _selection_page(path: Path, *, instrument: str, session: str, observation: str, records: list[object], checkpoint_unit: str | None = None, run_id: str = "fixture-run") -> None:
    payload = {"trades": records}
    frame = pd.DataFrame([{
        "provider": "DNSE", "dataset": "trades_history", "instrument": instrument,
        "source_event_time": session, "observation_id": observation,
        "raw_payload_hash": shadow._sha256(payload), "raw_payload_json": json.dumps(payload),
        "provenance_json": json.dumps({"ingestion_run_id": run_id, "checkpoint_identity": "fixture-checkpoint",
                                        "checkpoint_unit_id": checkpoint_unit or f"{instrument}__{session.replace('-', '')}__page"}),
    }])
    frame.to_parquet(path)


def _coverage(*, instrument: str, session: str, anchor: Path, observation: str, records: int, logical_status: str = shadow.ORIGINAL_SUCCESS, repair: dict | None = None) -> dict:
    unit = {
        "session": session, "instrument": instrument, "logical_status": logical_status,
        "original_status": "failed" if repair is not None else "success",
        "source_raw_file": None if repair is not None else str(anchor),
        "source_observation_id": None if repair is not None else observation,
        "original_records": None if repair is not None else records,
        "repair": repair,
    }
    return shadow._unit_selection(unit)


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


def test_page_index_is_once_per_directory_and_never_reads_unrelated_symbol(tmp_path: Path, monkeypatch):
    # A future suffix session verifies that page lookup has no 40-session range dependency.
    session, raw = "2026-09-04", tmp_path / "raw"
    raw.mkdir()
    aaa_first, aaa_second, bbb = raw / "AAA__01.parquet", raw / "AAA__02.parquet", raw / "BBB__01.parquet"
    _selection_page(aaa_first, instrument="AAA", session=session, observation="aaa-1", records=[{"id": 1}])
    _selection_page(aaa_second, instrument="AAA", session=session, observation="aaa-2", records=[{"id": 2}])
    _selection_page(bbb, instrument="BBB", session=session, observation="bbb-1", records=[{"id": 3}])
    reads, source_row = [], shadow._source_row

    def tracked(path):
        reads.append(Path(path).name)
        return source_row(path)

    monkeypatch.setattr(shadow, "_source_row", tracked)
    index = shadow._PageSelectionIndex()
    aaa = _coverage(instrument="AAA", session=session, anchor=aaa_first, observation="aaa-1", records=2)
    bbb_coverage = _coverage(instrument="BBB", session=session, anchor=bbb, observation="bbb-1", records=1)
    selected_aaa = shadow._select_pages(aaa, page_index=index)
    selected_bbb = shadow._select_pages(bbb_coverage, page_index=index)
    assert [Path(row["raw_file"]).name for row in selected_aaa] == ["AAA__01.parquet", "AAA__02.parquet"]
    assert [Path(row["raw_file"]).name for row in selected_bbb] == ["BBB__01.parquet"]
    assert index.operation_counts() == {"directory_enumerations": 1, "candidate_path_lookups": 2, "candidate_parquet_reads": 3, "indexed_directories": 1}
    assert reads.count("BBB__01.parquet") == 2  # BBB anchor plus its own candidate validation only.
    assert reads.count("AAA__01.parquet") == 2 and reads.count("AAA__02.parquet") == 1


def test_page_index_uses_exact_symbol_key_not_ticker_prefix(tmp_path: Path):
    raw = tmp_path / "raw"
    raw.mkdir()
    for instrument in ("A", "AA", "AAA"):
        _selection_page(raw / f"{instrument}__page.parquet", instrument=instrument, session="2026-08-11", observation=instrument, records=[])
    index = shadow._PageSelectionIndex()
    assert [path.name for path in index.candidates(raw, "A")] == ["A__page.parquet"]
    assert [path.name for path in index.candidates(raw, "AA")] == ["AA__page.parquet"]
    assert [path.name for path in index.candidates(raw, "AAA")] == ["AAA__page.parquet"]
    assert index.operation_counts()["directory_enumerations"] == 1


def test_repair_selection_uses_repair_pages_and_empty_and_missing_states_remain_distinct(tmp_path: Path):
    session = "2026-08-11"
    original, repair = tmp_path / "original", tmp_path / "repair"
    original.mkdir(); repair.mkdir()
    original_page, repair_page = original / "AAA__old.parquet", repair / "AAA__new.parquet"
    _selection_page(original_page, instrument="AAA", session=session, observation="original", records=[{"id": "old"}], run_id="original-run")
    _selection_page(repair_page, instrument="AAA", session=session, observation="repair", records=[{"id": "new"}], run_id="repair-run")
    repaired = _coverage(instrument="AAA", session=session, anchor=repair_page, observation="repair", records=1, logical_status=shadow.REPAIR_RECOVERED_SUCCESS,
                         repair={"repair_outcome": "success", "repair_raw_file": str(repair_page), "repair_observation_id": "repair", "repair_records": 1})
    selected = shadow._select_pages(repaired, page_index=shadow._PageSelectionIndex())
    assert [Path(row["raw_file"]).resolve() for row in selected] == [repair_page.resolve()]
    empty_page = original / "BBB__empty.parquet"
    _selection_page(empty_page, instrument="BBB", session=session, observation="empty", records=[])
    empty = _coverage(instrument="BBB", session=session, anchor=empty_page, observation="empty", records=0, logical_status=shadow.ORIGINAL_SUCCESS_EMPTY)
    assert shadow._select_pages(empty, page_index=shadow._PageSelectionIndex()) == []
    assert empty["empty_evidence"]["observation_id"] == "empty"
    assert empty["selected_raw_file"] is None
    failed = shadow._unit_selection({"session": session, "instrument": "CCC", "logical_status": shadow.REMAINING_FAILED, "original_status": "failed", "repair": {"repair_outcome": "failed"}})
    assert shadow._select_pages(failed, page_index=shadow._PageSelectionIndex()) == []
    assert failed["selected_attempt"] == shadow.REMAINING_FAILED


def test_missing_candidate_and_duplicate_candidate_identity_fail_or_preserve_existing_selection_behavior(tmp_path: Path):
    session, raw = "2026-08-11", tmp_path / "raw"
    raw.mkdir()
    missing = raw / "AAA__missing.parquet"
    _selection_page(missing, instrument="AAA", session=session, observation="missing", records=[{"id": 1}], checkpoint_unit="AAA__other__page")
    coverage = _coverage(instrument="AAA", session=session, anchor=missing, observation="missing", records=1)
    with pytest.raises(shadow.ReconciliationCanonicalAdapterError, match="SELECTED_PAGE_SET_ACCOUNTING_MISMATCH"):
        shadow._select_pages(coverage, page_index=shadow._PageSelectionIndex())
    first, second = raw / "BBB__01.parquet", raw / "BBB__02.parquet"
    _selection_page(first, instrument="BBB", session=session, observation="same-observation", records=[{"id": 1}])
    _selection_page(second, instrument="BBB", session=session, observation="same-observation", records=[{"id": 1}])
    duplicate = _coverage(instrument="BBB", session=session, anchor=first, observation="same-observation", records=2)
    selected = shadow._select_pages(duplicate, page_index=shadow._PageSelectionIndex())
    assert [row["expected_observation_id"] for row in selected] == ["same-observation", "same-observation"]
    assert [Path(row["raw_file"]).name for row in selected] == ["BBB__01.parquet", "BBB__02.parquet"]
