"""Reconciliation-selected, lineage-preserving DNSE Trades materialization.

This is the current-main restoration of the Task-160 adapter.  It accepts only
a terminal reconciliation contract, preserves unsuccessful units as coverage
records, and materializes selected raw pages into an independent shadow root.
It neither acquires data nor upgrades any data authority.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import csv
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Iterable, Mapping

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from atomic_io import atomic_write_json


SCHEMA_VERSION = "trades_canonical_shadow_v1"
COMPOSITE_COHORT_SCHEMA_VERSION = "trades_reconciliation_composite_cohort_v1"
COMPOSITE_COVERAGE_SCHEMA_VERSION = "trades_reconciliation_composite_coverage_v1"
PROVIDER = "DNSE"
DATASET = "trades_history"
KNOWN_BOARD_IDS = frozenset({"G1", "G4", "T1", "T3", "T4", "T6"})
ORIGINAL_SUCCESS = "ORIGINAL_SUCCESS"
ORIGINAL_SUCCESS_EMPTY = "ORIGINAL_SUCCESS_EMPTY"
REPAIR_RECOVERED_SUCCESS = "REPAIR_RECOVERED_SUCCESS"
REPAIR_RECOVERED_SUCCESS_EMPTY = "REPAIR_RECOVERED_SUCCESS_EMPTY"
REMAINING_FAILED = "REMAINING_FAILED"
LOGICAL_STATUSES = frozenset({ORIGINAL_SUCCESS, ORIGINAL_SUCCESS_EMPTY, REPAIR_RECOVERED_SUCCESS, REPAIR_RECOVERED_SUCCESS_EMPTY, REMAINING_FAILED})
_VN_TZ = timezone(timedelta(hours=7))

CANONICAL_SCHEMA = pa.schema([
    pa.field("schema_version", pa.string(), nullable=False),
    pa.field("provider", pa.string(), nullable=False),
    pa.field("dataset", pa.string(), nullable=False),
    pa.field("symbol", pa.string(), nullable=True),
    pa.field("session_date", pa.string(), nullable=False),
    pa.field("raw_timestamp", pa.string(), nullable=True),
    pa.field("timestamp_normalized", pa.timestamp("ms", tz="Asia/Ho_Chi_Minh"), nullable=True),
    pa.field("price", pa.float64(), nullable=True),
    pa.field("quantity", pa.float64(), nullable=True),
    pa.field("board_id", pa.string(), nullable=True),
    pa.field("board_semantic_review_required", pa.bool_(), nullable=False),
    pa.field("source_run_id", pa.string(), nullable=False),
    pa.field("source_page_identity", pa.string(), nullable=False),
    pa.field("source_page_payload_hash", pa.string(), nullable=False),
    pa.field("source_record_index", pa.int32(), nullable=False),
    pa.field("raw_record_identity", pa.string(), nullable=False),
])
QUARANTINE_SCHEMA = pa.schema([
    pa.field("schema_version", pa.string(), nullable=False), pa.field("session_date", pa.string(), nullable=False),
    pa.field("source_page_identity", pa.string(), nullable=False), pa.field("source_record_index", pa.int32(), nullable=False),
    pa.field("raw_record_identity", pa.string(), nullable=False), pa.field("reason", pa.string(), nullable=False),
    pa.field("raw_record_json", pa.string(), nullable=True),
])


class ReconciliationCanonicalAdapterError(ValueError):
    """A reconciled raw-selection contract cannot safely become canonical input."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)


def _sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ReconciliationCanonicalAdapterError(f"{label}_UNREADABLE:{path}") from exc


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReconciliationCanonicalAdapterError(f"{label}_MISSING")
    return value.strip()


def canonical_identity(*, provider: str, dataset: str, symbol: str | None, session_date: str, page_identity: str, payload_hash: str, record_index: int) -> str:
    return _sha256({"provider": provider, "dataset": dataset, "symbol": symbol, "session_date": session_date,
                    "source_page_identity": page_identity, "source_page_payload_hash": payload_hash,
                    "source_record_index": record_index})


def normalize_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for pattern in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, pattern).replace(tzinfo=_VN_TZ)
        except ValueError:
            pass
    try:
        result = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return result.replace(tzinfo=_VN_TZ) if result.tzinfo is None else result.astimezone(_VN_TZ)


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def _source_row(path: Path) -> dict[str, Any]:
    try:
        frame = pd.read_parquet(path)
    except (OSError, ValueError) as exc:
        raise ReconciliationCanonicalAdapterError(f"RAW_PAGE_UNREADABLE:{path}") from exc
    if len(frame) != 1:
        raise ReconciliationCanonicalAdapterError(f"RAW_PAGE_NOT_SINGLE_OBSERVATION:{path}")
    return frame.iloc[0].to_dict()


def _lineage(source: Mapping[str, Any]) -> tuple[str, str, str, str]:
    provider, dataset = str(source.get("provider") or PROVIDER), str(source.get("dataset") or DATASET)
    observation, payload_hash = str(source.get("observation_id") or ""), str(source.get("raw_payload_hash") or "")
    if not observation or not payload_hash:
        raise ReconciliationCanonicalAdapterError("RAW_PAGE_LINEAGE_MISSING")
    return provider, dataset, observation, payload_hash


def _raw_payload(source: Mapping[str, Any], path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(str(source["raw_payload_json"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ReconciliationCanonicalAdapterError(f"RAW_PAYLOAD_UNREADABLE:{path}") from exc
    if not isinstance(payload, Mapping) or _sha256(payload) != str(source.get("raw_payload_hash") or ""):
        raise ReconciliationCanonicalAdapterError(f"RAW_PAYLOAD_IDENTITY_DRIFT:{path}")
    return payload


def _stage_a_binding(checkpoint_path: Path) -> dict[str, str]:
    checkpoint = _load_json(checkpoint_path.resolve(), "STAGE_A_CHECKPOINT")
    if not isinstance(checkpoint, Mapping) or checkpoint.get("checkpoint_identity") != "TRADES_FINAL_COMPOSITE_CORPUS_CHECKPOINT_V1":
        raise ReconciliationCanonicalAdapterError("UNSUPPORTED_STAGE_A_CHECKPOINT_CONTRACT")
    binding = checkpoint.get("zero_writer_attestation")
    if not isinstance(binding, Mapping) or binding.get("observed_active_writers") != 0:
        raise ReconciliationCanonicalAdapterError("STAGE_A_ZERO_WRITER_BINDING_INVALID")
    attestation = Path(_text(binding.get("path"), "STAGE_A_ZERO_WRITER_ATTESTATION_PATH"))
    if not attestation.is_file():
        raise ReconciliationCanonicalAdapterError("STAGE_A_ZERO_WRITER_ATTESTATION_MISSING")
    if binding.get("sha256") != _file_sha256(attestation):
        raise ReconciliationCanonicalAdapterError("STAGE_A_ZERO_WRITER_ATTESTATION_IDENTITY_DRIFT")
    return {"checkpoint_path": str(checkpoint_path.resolve()), "checkpoint_sha256": _file_sha256(checkpoint_path),
            "zero_writer_attestation_path": str(attestation.resolve()), "zero_writer_attestation_sha256": _file_sha256(attestation)}


def _session_rows(path: Path) -> list[dict[str, Any]]:
    fields = ("session", "original_successful", "original_success_empty", "originally_failed", "repaired_success", "repaired_success_empty", "remaining_failed", "final_logical_success", "final_logical_failure", "consistency_state")
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or []) != fields:
                raise ReconciliationCanonicalAdapterError("RECONCILIATION_SESSIONS_SCHEMA_INVALID")
            rows = list(reader)
    except OSError as exc:
        raise ReconciliationCanonicalAdapterError(f"RECONCILIATION_SESSIONS_UNREADABLE:{path}") from exc
    result = []
    for row in rows:
        try:
            result.append({"session": _text(row.get("session"), "RECONCILIATION_SESSION"),
                           **{field: int(_text(row.get(field), f"RECONCILIATION_{field}")) for field in fields[1:-1]},
                           "consistency_state": _text(row.get("consistency_state"), "RECONCILIATION_CONSISTENCY_STATE")})
        except ValueError as exc:
            raise ReconciliationCanonicalAdapterError("RECONCILIATION_SESSION_VALUE_INVALID") from exc
    return result


def _unit_selection(unit: Mapping[str, Any]) -> dict[str, Any]:
    session, instrument = _text(unit.get("session"), "LOGICAL_UNIT_SESSION"), _text(unit.get("instrument"), "LOGICAL_UNIT_INSTRUMENT").upper()
    status, original_status = _text(unit.get("logical_status"), "LOGICAL_STATUS"), _text(unit.get("original_status"), "ORIGINAL_STATUS")
    if status not in LOGICAL_STATUSES:
        raise ReconciliationCanonicalAdapterError(f"UNSUPPORTED_LOGICAL_STATUS:{session}:{instrument}:{status}")
    result = {"logical_unit_id": f"{session}:{instrument}", "session": session, "instrument": instrument,
              "logical_status": status, "original": {"status": original_status, "raw_file": unit.get("source_raw_file"),
              "observation_id": unit.get("source_observation_id"), "records": unit.get("original_records"), "error_code": unit.get("original_error_code")},
              "repair": unit.get("repair"), "selected_attempt": None, "selected_raw_file": None,
              "selected_observation_id": None, "selected_raw_payload_hash": None, "selected_raw_pages": [],
              "selected_raw_record_count": 0, "empty_evidence": None}
    if status in (ORIGINAL_SUCCESS, ORIGINAL_SUCCESS_EMPTY):
        if original_status != "success" or unit.get("repair") is not None:
            raise ReconciliationCanonicalAdapterError(f"ORIGINAL_SELECTION_CONTRACT_VIOLATION:{result['logical_unit_id']}")
        result["selected_attempt"] = "ORIGINAL" if status == ORIGINAL_SUCCESS else "ORIGINAL_SUCCESS_EMPTY"
        result["selected_raw_file"] = result["original"]["raw_file"]
        result["selected_observation_id"] = result["original"]["observation_id"]
    else:
        repair = result["repair"]
        if original_status != "failed" or not isinstance(repair, Mapping):
            raise ReconciliationCanonicalAdapterError(f"REPAIR_SELECTION_CONTRACT_VIOLATION:{result['logical_unit_id']}")
        if status == REMAINING_FAILED:
            if repair.get("repair_outcome") != "failed":
                raise ReconciliationCanonicalAdapterError(f"REMAINING_FAILED_OUTCOME_MISMATCH:{result['logical_unit_id']}")
            result["selected_attempt"] = REMAINING_FAILED
        else:
            if repair.get("repair_outcome") != "success":
                raise ReconciliationCanonicalAdapterError(f"RECOVERED_SELECTION_OUTCOME_MISMATCH:{result['logical_unit_id']}")
            result["selected_attempt"] = "REPAIR" if status == REPAIR_RECOVERED_SUCCESS else "REPAIR_RECOVERED_SUCCESS_EMPTY"
            result["selected_raw_file"] = repair.get("repair_raw_file")
            result["selected_observation_id"] = repair.get("repair_observation_id")
    return result


def _select_pages(coverage: dict[str, Any]) -> list[dict[str, Any]]:
    if coverage["selected_attempt"] == REMAINING_FAILED:
        return []
    anchor_path = Path(_text(coverage.get("selected_raw_file"), "SELECTED_RAW_FILE")).resolve()
    anchor = _source_row(anchor_path)
    provider, dataset, observation, payload_hash = _lineage(anchor)
    if provider != PROVIDER or dataset != DATASET or observation != coverage["selected_observation_id"]:
        raise ReconciliationCanonicalAdapterError(f"SELECTED_ANCHOR_IDENTITY_DRIFT:{coverage['logical_unit_id']}")
    payload = _raw_payload(anchor, anchor_path)
    is_empty = coverage["logical_status"] in (ORIGINAL_SUCCESS_EMPTY, REPAIR_RECOVERED_SUCCESS_EMPTY)
    if is_empty:
        if payload.get("trades") != []:
            raise ReconciliationCanonicalAdapterError(f"SUCCESS_EMPTY_PAYLOAD_NOT_EMPTY:{coverage['logical_unit_id']}")
        coverage["empty_evidence"] = {"raw_file": str(anchor_path), "observation_id": observation, "raw_payload_hash": payload_hash, "raw_file_sha256": _file_sha256(anchor_path)}
        coverage["selected_raw_file"] = None
        coverage["selected_observation_id"] = None
        coverage["selected_raw_payload_hash"] = None
        return []
    try:
        provenance = json.loads(str(anchor["provenance_json"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ReconciliationCanonicalAdapterError(f"SELECTED_ANCHOR_PROVENANCE_UNREADABLE:{coverage['logical_unit_id']}") from exc
    selected, total_records = [], 0
    prefix = f"{coverage['instrument']}__{coverage['session'].replace('-', '')}__"
    for path in sorted(anchor_path.parent.glob("*.parquet"), key=str):
        source = _source_row(path)
        if str(source.get("instrument") or "").upper() != coverage["instrument"] or str(source.get("source_event_time") or "") != coverage["session"]:
            continue
        try:
            page_provenance = json.loads(str(source["provenance_json"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ReconciliationCanonicalAdapterError(f"SELECTED_PAGE_PROVENANCE_UNREADABLE:{path}") from exc
        if page_provenance.get("ingestion_run_id") != provenance.get("ingestion_run_id") or page_provenance.get("checkpoint_identity") != provenance.get("checkpoint_identity") or not str(page_provenance.get("checkpoint_unit_id") or "").startswith(prefix):
            continue
        records = _raw_payload(source, path).get("trades")
        if not isinstance(records, list):
            raise ReconciliationCanonicalAdapterError(f"SELECTED_PAGE_TRADES_CONTRACT_INVALID:{path}")
        _, _, page_observation, page_hash = _lineage(source)
        total_records += len(records)
        selected.append({"raw_file": str(path.resolve()), "logical_unit_id": coverage["logical_unit_id"], "logical_status": coverage["logical_status"],
                         "selected_attempt": coverage["selected_attempt"], "expected_observation_id": page_observation,
                         "expected_raw_payload_hash": page_hash, "raw_file_sha256": _file_sha256(path)})
    expected = coverage["original"]["records"] if coverage["selected_attempt"] == "ORIGINAL" else coverage["repair"].get("repair_records")
    if not selected or total_records != expected or str(anchor_path) not in {item["raw_file"] for item in selected}:
        raise ReconciliationCanonicalAdapterError(f"SELECTED_PAGE_SET_ACCOUNTING_MISMATCH:{coverage['logical_unit_id']}")
    coverage["selected_raw_payload_hash"], coverage["selected_raw_record_count"], coverage["selected_raw_pages"] = payload_hash, total_records, selected
    return selected


def _final_review_snapshot(root: Path | str | None, *, reconciliation_identity: str, session_universe: list[str]) -> dict[str, Any] | None:
    if root is None:
        return None
    review_root = Path(root).resolve()
    manifest_path, quality_path = review_root / "final_trades_review_manifest.json", review_root / "final_trades_session_quality.csv"
    manifest = _load_json(manifest_path, "FINAL_REVIEW_MANIFEST")
    if not isinstance(manifest, Mapping) or manifest.get("reconciliation_output_identity") != reconciliation_identity or list(manifest.get("session_universe") or []) != session_universe:
        raise ReconciliationCanonicalAdapterError("FINAL_REVIEW_RECONCILIATION_OR_SESSION_MISMATCH")
    try:
        quality = pd.read_csv(quality_path).fillna("").to_dict(orient="records")
    except (OSError, ValueError) as exc:
        raise ReconciliationCanonicalAdapterError(f"FINAL_REVIEW_QUALITY_UNREADABLE:{quality_path}") from exc
    if [str(row.get("session")) for row in quality] != session_universe:
        raise ReconciliationCanonicalAdapterError("FINAL_REVIEW_QUALITY_SESSION_ORDER_MISMATCH")
    return {"review_manifest_path": str(manifest_path), "review_manifest_sha256": _file_sha256(manifest_path),
            "review_identity": _text(manifest.get("deterministic_review_sha256"), "FINAL_REVIEW_IDENTITY"),
            "session_quality_path": str(quality_path), "session_quality_sha256": _file_sha256(quality_path), "sessions": quality}


def build_reconciliation_composite_cohort(*, reconciliation_root: Path | str, output_root: Path | str, stage_a_checkpoint_path: Path | str, final_review_root: Path | str | None = None, on_progress: Callable[[int, int], None] | None = None) -> dict[str, Any]:
    """Build coverage and exact raw selection without copying, deleting, or acquiring raw data."""
    reconciliation, root = Path(reconciliation_root).resolve(), Path(output_root).resolve()
    manifest_path, units_path, summary_path, sessions_path = (reconciliation / "reconciliation_manifest.json", reconciliation / "reconciliation_units.json", reconciliation / "reconciliation_summary.json", reconciliation / "reconciliation_sessions.csv")
    manifest, units, summary, sessions = _load_json(manifest_path, "RECONCILIATION_MANIFEST"), _load_json(units_path, "RECONCILIATION_UNITS"), _load_json(summary_path, "RECONCILIATION_SUMMARY"), _session_rows(sessions_path)
    if not isinstance(manifest, Mapping) or manifest.get("tooling_version") != "TRADES_POST_REPAIR_RECONCILIATION_V1" or not isinstance(units, list) or not isinstance(summary, Mapping):
        raise ReconciliationCanonicalAdapterError("UNSUPPORTED_RECONCILIATION_CONTRACT")
    session_universe = list(manifest.get("session_universe") or [])
    if not session_universe or [row["session"] for row in sessions] != session_universe or manifest.get("instrument_session_unit_count") != len(units) or summary.get("unit_count") != len(units):
        raise ReconciliationCanonicalAdapterError("RECONCILIATION_ACCOUNTING_INVALID")
    identity_fields = ("source_tranche_id", "source_terminal_identity", "repair_plan_hash", "executor_plan_hash", "repair_runtime_identity")
    try:
        recomputed_identity = _sha256({**{field: _text(manifest.get(field), f"RECONCILIATION_{field}") for field in identity_fields},
                                       "sessions": sessions, "units": units, "summary": dict(summary)})
    except ReconciliationCanonicalAdapterError:
        raise
    if recomputed_identity != _text(manifest.get("deterministic_output_sha256"), "RECONCILIATION_OUTPUT_IDENTITY"):
        raise ReconciliationCanonicalAdapterError("RECONCILIATION_OUTPUT_IDENTITY_MISMATCH")
    stage_binding = _stage_a_binding(Path(stage_a_checkpoint_path))
    final_review = _final_review_snapshot(final_review_root, reconciliation_identity=recomputed_identity, session_universe=session_universe)
    coverage, selected_by_session, seen = [], {session: [] for session in session_universe}, set()
    for index, unit in enumerate(units):
        if not isinstance(unit, Mapping):
            raise ReconciliationCanonicalAdapterError("RECONCILIATION_UNIT_NOT_MAPPING")
        item = _unit_selection(unit)
        key = (item["session"], item["instrument"])
        if item["session"] not in selected_by_session or key in seen:
            raise ReconciliationCanonicalAdapterError("RECONCILIATION_LOGICAL_UNIT_INVALID_OR_DUPLICATE")
        seen.add(key)
        pages = _select_pages(item)
        selected_by_session[item["session"]].extend(pages)
        coverage.append(item)
        if on_progress is not None:
            on_progress(index + 1, len(units))
    coverage_payload = {"schema_version": COMPOSITE_COVERAGE_SCHEMA_VERSION, "reconciliation_manifest_sha256": _file_sha256(manifest_path),
                        "reconciliation_units_sha256": _file_sha256(units_path), "reconciliation_summary_sha256": _file_sha256(summary_path),
                        "reconciliation_sessions_sha256": _file_sha256(sessions_path), "reconciliation_output_identity": manifest.get("deterministic_output_sha256"),
                        "stage_a_zero_writer_binding": stage_binding, "session_universe": session_universe, "units": coverage, "final_review": final_review}
    coverage_hash = _sha256(coverage_payload)
    selected_pages = [page for session in session_universe for page in selected_by_session[session]]
    selection_payload = {"reconciliation_output_identity": manifest.get("deterministic_output_sha256"), "stage_a_zero_writer_binding": stage_binding,
                         "selected_logical_units": [{key: item[key] for key in ("logical_unit_id", "logical_status", "selected_attempt", "selected_raw_file", "selected_raw_payload_hash", "selected_raw_pages", "selected_raw_record_count")} for item in coverage],
                         "selected_pages": selected_pages}
    selection_hash = _sha256(selection_payload)
    root.mkdir(parents=True, exist_ok=True)
    coverage_path = root / "composite_unit_coverage.json"
    cohort = {"schema_version": COMPOSITE_COHORT_SCHEMA_VERSION, "canonical_input_contract": SCHEMA_VERSION,
              "cohort_id": f"trades-reconciliation-composite-{selection_hash[:16]}", "source_runtime_root": "IMMUTABLE_RECONCILIATION_SELECTION_ONLY",
              "sessions": [{"session_date": session, "selected_raw_files": selected_by_session[session]} for session in session_universe],
              "reconciliation_selection": {"reconciliation_root": str(reconciliation), "reconciliation_output_identity": manifest.get("deterministic_output_sha256"),
              "stage_a_zero_writer_binding": stage_binding, "selected_logical_units_sha256": selection_hash, "coverage_sha256": coverage_hash, "coverage_file": str(coverage_path.resolve()), "final_review": final_review}}
    cohort_path, selection_path = root / "composite_cohort_manifest.json", root / "selected_raw_pages.json"
    atomic_write_json(coverage_path, coverage_payload)
    atomic_write_json(selection_path, {"schema_version": COMPOSITE_COHORT_SCHEMA_VERSION, **selection_payload})
    atomic_write_json(cohort_path, cohort)
    return {"cohort_manifest": str(cohort_path), "coverage": str(coverage_path), "selection": str(selection_path), "cohort": cohort,
            "coverage_summary": dict(Counter(item["logical_status"] for item in coverage))}


def _atomic_parquet(path: Path, rows: list[dict[str, Any]], schema: pa.Schema) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".tmp-{path.name}-", suffix=".parquet", dir=path.parent)
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        pq.write_table(pa.Table.from_pylist(rows, schema=schema), temporary, compression="zstd", version="2.6", use_dictionary=True, write_statistics=True)
        pq.ParquetFile(temporary).metadata
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _canonical_row(record: Mapping[str, Any], source: Mapping[str, Any], session: str, index: int) -> dict[str, Any]:
    provider, dataset, page, payload_hash = _lineage(source)
    symbol = record.get("symbol") if isinstance(record.get("symbol"), str) else source.get("instrument")
    symbol = str(symbol).upper() if symbol else None
    board = str(record.get("boardId")) if record.get("boardId") is not None else None
    raw_timestamp = str(record.get("time")) if record.get("time") is not None else None
    try:
        source_run_id = str(json.loads(str(source.get("provenance_json") or "{}")).get("ingestion_run_id") or "")
    except ValueError:
        source_run_id = ""
    return {"schema_version": SCHEMA_VERSION, "provider": provider, "dataset": dataset, "symbol": symbol, "session_date": session,
            "raw_timestamp": raw_timestamp, "timestamp_normalized": normalize_timestamp(raw_timestamp), "price": _number(record.get("matchPrice")),
            "quantity": _number(record.get("matchQtty")), "board_id": board, "board_semantic_review_required": board not in KNOWN_BOARD_IDS,
            "source_run_id": source_run_id, "source_page_identity": page, "source_page_payload_hash": payload_hash,
            "source_record_index": index, "raw_record_identity": canonical_identity(provider=provider, dataset=dataset, symbol=symbol, session_date=session, page_identity=page, payload_hash=payload_hash, record_index=index)}


def _materialize_session(entry: Mapping[str, Any], root: Path) -> dict[str, Any]:
    session, rows, quarantine, identities = _text(entry.get("session_date"), "COHORT_SESSION"), [], [], set()
    selected_files = entry.get("selected_raw_files")
    if selected_files is None:
        raw_dir = Path(_text(entry.get("raw_dir"), "COHORT_RAW_DIR"))
        selected_files = []
        for raw_path in sorted(raw_dir.glob("*.parquet"), key=str):
            raw_source = _source_row(raw_path)
            _, _, raw_observation, raw_hash = _lineage(raw_source)
            selected_files.append({"raw_file": str(raw_path), "raw_file_sha256": _file_sha256(raw_path),
                                   "expected_observation_id": raw_observation, "expected_raw_payload_hash": raw_hash})
    if not isinstance(selected_files, list):
        raise ReconciliationCanonicalAdapterError("COHORT_SELECTED_RAW_FILES_INVALID")
    for selected in selected_files:
        path = Path(_text(selected.get("raw_file"), "SELECTED_RAW_FILE"))
        if not path.is_file() or _file_sha256(path) != _text(selected.get("raw_file_sha256"), "SELECTED_RAW_FILE_SHA256"):
            raise ReconciliationCanonicalAdapterError(f"SELECTED_RAW_FILE_IDENTITY_DRIFT:{path}")
        source = _source_row(path)
        _, _, page, payload_hash = _lineage(source)
        if page != _text(selected.get("expected_observation_id"), "EXPECTED_OBSERVATION_ID") or payload_hash != _text(selected.get("expected_raw_payload_hash"), "EXPECTED_RAW_PAYLOAD_HASH"):
            raise ReconciliationCanonicalAdapterError(f"SELECTED_RAW_PAGE_LINEAGE_DRIFT:{path}")
        records = _raw_payload(source, path).get("trades")
        if not isinstance(records, list):
            raise ReconciliationCanonicalAdapterError(f"SELECTED_RAW_TRADES_CONTRACT_INVALID:{path}")
        for index, record in enumerate(records):
            if not isinstance(record, Mapping):
                quarantine.append({"schema_version": SCHEMA_VERSION, "session_date": session, "source_page_identity": page, "source_record_index": index,
                                   "raw_record_identity": canonical_identity(provider=PROVIDER, dataset=DATASET, symbol=None, session_date=session, page_identity=page, payload_hash=payload_hash, record_index=index),
                                   "reason": "trade_record_not_an_object", "raw_record_json": canonical_json(record)})
                continue
            row = _canonical_row(record, source, session, index)
            if row["raw_record_identity"] in identities:
                raise ReconciliationCanonicalAdapterError(f"DUPLICATE_CANONICAL_IDENTITY:{session}")
            identities.add(row["raw_record_identity"])
            rows.append(row)
    output = root / "canonical" / "provider=DNSE" / "dataset=trades_history" / f"session_date={session}" / "part-00000.parquet"
    _atomic_parquet(output, rows, CANONICAL_SCHEMA)
    if quarantine:
        _atomic_parquet(root / "canonical" / "quarantine" / f"session_date={session}" / "part-00000.parquet", quarantine, QUARANTINE_SCHEMA)
    return {"session_date": session, "source_records": len(rows) + len(quarantine), "canonical_rows": len(rows), "quarantined_records": len(quarantine), "missing_records": 0,
            "duplicate_identities": 0, "output_file": str(output), "output_bytes": output.stat().st_size,
            "quality": {"timestamp_violations": sum(row["timestamp_normalized"] is not None and row["timestamp_normalized"].date().isoformat() != session for row in rows),
                        "invalid_prices": sum(row["price"] is not None and row["price"] <= 0 for row in rows), "invalid_quantities": sum(row["quantity"] is not None and row["quantity"] < 0 for row in rows),
                        "unknown_board_codes": sorted({str(row["board_id"]) for row in rows if row["board_semantic_review_required"] and row["board_id"]}), "null_key_fields": sum(any(row[key] is None for key in ("symbol", "raw_timestamp", "price", "quantity", "board_id")) for row in rows)}}


def materialize_cohort(*, cohort_manifest_path: Path | str, shadow_root: Path | str, workers: int = 3) -> dict[str, Any]:
    """Materialize a selected cohort idempotently. ``workers`` is retained for CLI compatibility."""
    if workers <= 0:
        raise ValueError("workers_must_be_positive")
    cohort_path, root = Path(cohort_manifest_path), Path(shadow_root)
    cohort = _load_json(cohort_path, "COHORT_MANIFEST")
    if not isinstance(cohort, Mapping):
        raise ReconciliationCanonicalAdapterError("COHORT_MANIFEST_NOT_MAPPING")
    if cohort.get("schema_version") == COMPOSITE_COHORT_SCHEMA_VERSION and cohort.get("canonical_input_contract") != SCHEMA_VERSION:
        raise ReconciliationCanonicalAdapterError("COHORT_CANONICAL_CONTRACT_MISMATCH")
    cohort_hash, result_path = _file_sha256(cohort_path), root / "materialization_manifest.json"
    if result_path.is_file():
        prior = _load_json(result_path, "MATERIALIZATION_MANIFEST")
        if prior.get("cohort_manifest_sha256") == cohort_hash and all(Path(item["output_file"]).is_file() for item in prior.get("sessions") or []):
            return {**prior, "rerun_behavior": "SKIP_VERIFIED_MATERIALIZATION"}
    sessions = [_materialize_session(entry, root) for entry in cohort.get("sessions") or []]
    aggregate = {key: sum(int(item[key]) for item in sessions) for key in ("source_records", "canonical_rows", "quarantined_records", "missing_records", "duplicate_identities")}
    aggregate["output_files"], aggregate["output_bytes"] = len(sessions) + sum(item["quarantined_records"] > 0 for item in sessions), sum(item["output_bytes"] for item in sessions)
    aggregate["quality"] = {"timestamp_violations": sum(item["quality"]["timestamp_violations"] for item in sessions), "invalid_prices": sum(item["quality"]["invalid_prices"] for item in sessions), "invalid_quantities": sum(item["quality"]["invalid_quantities"] for item in sessions), "unknown_boards": sorted({board for item in sessions for board in item["quality"]["unknown_board_codes"]}), "null_key_fields": sum(item["quality"]["null_key_fields"] for item in sessions)}
    result = {"schema_version": SCHEMA_VERSION, "cohort_manifest_sha256": cohort_hash, "cohort_id": cohort.get("cohort_id"), "sessions": sessions, "aggregate": aggregate,
              "semantic_limitations": "RAW_PRESERVING; DIRECTIONAL_SEMANTICS_NOT_CREATED; SHADOW_ONLY", "rerun_behavior": "MATERIALIZED"}
    if cohort.get("reconciliation_selection") is not None:
        result["reconciliation_selection"] = cohort["reconciliation_selection"]
    if aggregate["source_records"] != aggregate["canonical_rows"] + aggregate["quarantined_records"]:
        raise ReconciliationCanonicalAdapterError("MATERIALIZATION_PARITY_FAILURE")
    atomic_write_json(result_path, result)
    return result
