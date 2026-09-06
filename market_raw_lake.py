"""Generic, provider/dataset-agnostic immutable raw-observation store plus a
checkpoint/manifest layer for the market-wide ingest-first raw data lake.

LAYOUT (all beneath the runtime root -- generated runtime data, never the
source repo, matching AGENTS.md's ``STOCK_LOOKUP_RUNTIME_ROOT`` contract)

    data/market_raw_lake/
        raw/<provider>/<dataset>/<run_id>/<unit_slug>__<observation_id16>.parquet
            One immutable file per successfully fetched unit of work. Never
            rewritten: re-persisting the same logical observation produces
            either the byte-identical file again (a true no-op, see
            ``write_raw_observation``) or a new file under a new ``run_id``
            (a new historical observation) -- never an overwrite of an
            existing file with different bytes.
        checkpoints/<provider>__<dataset>__<run_scope_id>.json
            Resumable state for one logical run scope: which units have been
            attempted and with what outcome. Rewritten atomically after every
            single unit, so an interrupted run loses at most the one
            in-flight unit, never previously completed work.
        manifests/<provider>__<dataset>__<run_id>.json
            One record per concrete run: requested/attempted/succeeded/
            failed/skipped units, timing, and output locations.

WHY ONE ROW == ONE FILE, NOT BATCHED
    A unit's checkpoint entry is only ever set to "success" by a caller
    *after* its raw Parquet file has been durably written (``atomic_io.
    atomic_write_file`` fsyncs before the atomic rename). Batching several
    units into one Parquet file would force a choice between delaying every
    one of their checkpoint updates until the batch flushes (losing
    already-fetched-but-unflushed work on a crash) or checkpointing before
    the flush (letting the checkpoint claim success for data that was never
    made durable) -- both defeat the point of a checkpoint. One file per unit
    keeps "checkpointed success" and "durably on disk" the same fact. If file
    count ever becomes an operational problem, a periodic batched flush with
    an all-or-nothing checkpoint update is a valid future optimization;
    nothing here forecloses it.

WHY THE RAW PAYLOAD IS AN OPAQUE COLUMN, NOT A FLATTENED TABLE
    ``market_data_contracts.RawObservation`` is this platform's raw-lake
    contract, and its ``raw_payload`` is intentionally opaque (whatever JSON
    the provider returned). Flattening a dataset's fields into real typed
    Parquet columns (e.g. separate open/high/low/close columns) is
    canonicalization -- Layer 2/3 work this milestone is not authorized to
    do (see ``docs/market_wide_ingest_first_architecture.md``'s layer
    table). This store is therefore genuinely dataset-agnostic: it never
    inspects ``raw_payload``'s internal shape.
"""
from __future__ import annotations

import copy
import io
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from atomic_io import atomic_write_file, atomic_write_json
from market_data_contracts import RawObservation
from vn_time import vn_now_iso

STORE_SCHEMA_VERSION = "1.0.0"
CHECKPOINT_SCHEMA_VERSION = "1.0.0"
MANIFEST_SCHEMA_VERSION = "1.0.0"

STORE_RELATIVE = Path("data") / "market_raw_lake"
RAW_RELATIVE = STORE_RELATIVE / "raw"
CHECKPOINTS_RELATIVE = STORE_RELATIVE / "checkpoints"
MANIFESTS_RELATIVE = STORE_RELATIVE / "manifests"

_UNIT_SLUG_SAFE = "-_."
_VALID_UNIT_STATUSES = ("success", "failed", "skipped")


class RawLakeImmutabilityError(RuntimeError):
    """A unit's raw file already exists on disk with different bytes than the
    write being attempted -- the one condition this store must never allow."""


class RunScopeLockedError(RuntimeError):
    """Another local process owns this provider/dataset checkpoint scope."""


def _slug(value: str) -> str:
    text = "".join(ch if ch.isalnum() or ch in _UNIT_SLUG_SAFE else "_" for ch in str(value))
    return text[:120] or "unit"


def store_root(runtime_root: Path | str) -> Path:
    return Path(runtime_root) / STORE_RELATIVE


def raw_run_dir(runtime_root: Path | str, provider: str, dataset: str, run_id: str) -> Path:
    return Path(runtime_root) / RAW_RELATIVE / provider / dataset / _slug(run_id)


def checkpoint_path(runtime_root: Path | str, provider: str, dataset: str, run_scope_id: str) -> Path:
    return Path(runtime_root) / CHECKPOINTS_RELATIVE / f"{provider}__{dataset}__{_slug(run_scope_id)}.json"


def run_scope_lock_path(runtime_root: Path | str, provider: str, dataset: str, run_scope_id: str) -> Path:
    return checkpoint_path(runtime_root, provider, dataset, run_scope_id).with_suffix(".lock")


def _lock_owner_is_definitely_dead(path: Path) -> bool:
    """Only reclaim a lock with a locally provable dead owner; otherwise fail closed."""
    try:
        fields = dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines()
                      if "=" in line)
        pid = int(fields["pid"])
    except (OSError, ValueError, KeyError):
        return False
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if handle:
            kernel32.CloseHandle(handle)
            return False
        return ctypes.get_last_error() == 87  # ERROR_INVALID_PARAMETER
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


@contextmanager
def exclusive_run_scope_lock(runtime_root: Path | str, provider: str, dataset: str, run_scope_id: str):
    """Acquire one deterministic checkpoint-scope writer lock or fail closed.

    A single stale-lock recovery attempt is allowed only for a verified dead
    local PID.  There is no polling or unbounded contention retry.
    """
    path = run_scope_lock_path(runtime_root, provider, dataset, run_scope_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError as exc:
        if _lock_owner_is_definitely_dead(path):
            path.unlink()
            try:
                fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            except FileExistsError as retry_exc:
                raise RunScopeLockedError(f"run scope is already active: {run_scope_id}") from retry_exc
        else:
            raise RunScopeLockedError(f"run scope is already active: {run_scope_id}") from exc
    try:
        os.write(fd, f"run_scope_id={run_scope_id}\npid={os.getpid()}\n".encode("utf-8"))
        yield
    finally:
        os.close(fd)
        path.unlink(missing_ok=True)


def manifest_path(runtime_root: Path | str, provider: str, dataset: str, run_id: str) -> Path:
    return Path(runtime_root) / MANIFESTS_RELATIVE / f"{provider}__{dataset}__{_slug(run_id)}.json"


def raw_file_path(runtime_root: Path | str, provider: str, dataset: str, run_id: str,
                  unit_id: str, observation_id: str) -> Path:
    return raw_run_dir(runtime_root, provider, dataset, run_id) / f"{_slug(unit_id)}__{observation_id[:16]}.parquet"


def _observation_frame(observation: RawObservation) -> pd.DataFrame:
    record = observation.record()
    row = {
        **{key: value for key, value in record.items() if key not in ("raw_payload", "provenance")},
        "raw_payload_json": json.dumps(record["raw_payload"], ensure_ascii=False, sort_keys=True, default=str),
        "provenance_json": json.dumps(record["provenance"], ensure_ascii=False, sort_keys=True, default=str),
    }
    return pd.DataFrame([row])


def _frame_to_parquet_bytes(frame: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    frame.to_parquet(buffer, engine="pyarrow", index=False)
    return buffer.getvalue()


def find_same_run_logical_observation(runtime_root: Path | str, observation: RawObservation,
                                      run_id: str) -> Path | None:
    """Find an already-retained logical provider response in one concrete run.

    This is intentionally a lookup, not an automatic write suppression:
    regular raw observations preserve distinct retrieval timestamps. Callers
    with an explicit idempotent replay contract (the universe page collector)
    may use it to avoid duplicate re-collection for the same ``run_id``.
    """
    directory = raw_run_dir(runtime_root, observation.provider, observation.dataset, run_id)
    expected = {
        "provider": observation.provider,
        "dataset": observation.dataset,
        "instrument": observation.instrument,
        "request_identity": observation.request_identity,
        "raw_payload_hash": observation.raw_payload_hash,
        "schema_version": observation.schema_version,
    }
    for candidate in sorted(directory.glob(f"{_slug(observation.instrument)}__*.parquet")):
        try:
            existing = pd.read_parquet(candidate, columns=list(expected))
        except Exception:  # malformed existing raw file is not a match to trust
            continue
        if len(existing) == 1 and all(str(existing.iloc[0][key]) == str(value)
                                      for key, value in expected.items()):
            return candidate
    return None


def write_raw_observation(runtime_root: Path | str, observation: RawObservation, *, run_id: str) -> dict[str, Any]:
    """Persist one RawObservation as an immutable Parquet file.

    The unit id is ``observation.instrument`` -- for a per-symbol dataset
    (e.g. OHLC) that is the ticker; for a market-wide listing dataset it is
    whatever page/unit label the caller chose when constructing the
    observation. Idempotent by content: if the target file already exists
    with the exact same bytes (the same observation persisted again, e.g.
    after a restart whose checkpoint update never landed), this is a true
    no-op. Existing-with-different-bytes should be structurally impossible
    since the filename embeds the content-derived ``observation_id``; if it
    ever happens anyway this raises rather than silently overwriting history.
    """
    path = raw_file_path(runtime_root, observation.provider, observation.dataset, run_id,
                         observation.instrument, observation.observation_id)
    content = _frame_to_parquet_bytes(_observation_frame(observation))
    if path.exists():
        if path.read_bytes() == content:
            return {"path": str(path), "written": False, "reason": "already_present_identical",
                    "observation_id": observation.observation_id}
        raise RawLakeImmutabilityError(f"raw file {path} exists with different content than this write")
    atomic_write_file(path, content)
    return {"path": str(path), "written": True, "observation_id": observation.observation_id,
            "bytes": len(content)}


def write_snapshot_parquet(path: Path | str, frame: pd.DataFrame) -> dict[str, Any]:
    """Write a whole-snapshot table (e.g. a universe listing) atomically.

    Unlike ``write_raw_observation``, a snapshot's immutability comes from
    the caller's own path-naming convention (typically containing a
    content-derived snapshot id), not from a check in this function --
    mirroring ``instrument_master_sync.py``'s existing ``snapshot_id``-keyed
    rows.
    """
    path = Path(path)
    content = _frame_to_parquet_bytes(frame)
    atomic_write_file(path, content)
    return {"path": str(path), "bytes": len(content), "rows": int(len(frame))}


def new_checkpoint(provider: str, dataset: str, run_scope_id: str) -> dict[str, Any]:
    now = vn_now_iso()
    return {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "provider": provider,
        "dataset": dataset,
        "run_scope_id": run_scope_id,
        "created_at": now,
        "updated_at": now,
        "units": {},
    }


def load_checkpoint(runtime_root: Path | str, provider: str, dataset: str, run_scope_id: str) -> dict[str, Any]:
    path = checkpoint_path(runtime_root, provider, dataset, run_scope_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return new_checkpoint(provider, dataset, run_scope_id)
    if not isinstance(payload, Mapping) or payload.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
        return new_checkpoint(provider, dataset, run_scope_id)
    return dict(payload)


def save_checkpoint(runtime_root: Path | str, checkpoint: Mapping[str, Any]) -> Path:
    path = checkpoint_path(runtime_root, checkpoint["provider"], checkpoint["dataset"], checkpoint["run_scope_id"])
    atomic_write_json(path, dict(checkpoint))
    return path


def unit_status(checkpoint: Mapping[str, Any], unit_id: str) -> str | None:
    unit = checkpoint.get("units", {}).get(unit_id)
    return unit.get("status") if isinstance(unit, Mapping) else None


def record_unit_result(checkpoint: Mapping[str, Any], unit_id: str, *, status: str,
                       raw_file: str | None = None, observation_id: str | None = None,
                       error_code: str | None = None) -> dict[str, Any]:
    """Pure: returns a *new* checkpoint dict with ``unit_id`` updated. The
    caller persists it via ``save_checkpoint`` immediately -- see the module
    docstring for why that ordering (write raw file, then checkpoint) matters."""
    if status not in _VALID_UNIT_STATUSES:
        raise ValueError(f"invalid unit status: {status!r}")
    updated = copy.deepcopy(dict(checkpoint))
    units = updated.setdefault("units", {})
    prior = units.get(unit_id) or {}
    now = vn_now_iso()
    units[unit_id] = {
        "status": status,
        "attempts": int(prior.get("attempts", 0)) + 1,
        "first_attempt_at": prior.get("first_attempt_at", now),
        "last_attempt_at": now,
        "raw_file": raw_file,
        "observation_id": observation_id,
        "error_code": error_code,
    }
    updated["updated_at"] = now
    return updated


def units_with_status(checkpoint: Mapping[str, Any], status: str) -> set[str]:
    return {unit_id for unit_id, info in checkpoint.get("units", {}).items()
           if isinstance(info, Mapping) and info.get("status") == status}


def completed_units(checkpoint: Mapping[str, Any]) -> set[str]:
    return units_with_status(checkpoint, "success")


def build_manifest(*, provider: str, dataset: str, run_id: str, run_scope_id: str,
                   started_at: str, ended_at: str, requested_units: list[str],
                   attempted_units: list[str], successful_units: list[str],
                   failed_units: list[dict[str, Any]], skipped_units: list[str],
                   output_dir: str, checkpoint_file: str,
                   extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "run_scope_id": run_scope_id,
        "provider": provider,
        "dataset": dataset,
        "started_at": started_at,
        "ended_at": ended_at,
        "requested_unit_count": len(requested_units),
        "attempted_unit_count": len(attempted_units),
        "successful_unit_count": len(successful_units),
        "failed_unit_count": len(failed_units),
        "skipped_unit_count": len(skipped_units),
        "requested_units": sorted(requested_units),
        "attempted_units": sorted(attempted_units),
        "successful_units": sorted(successful_units),
        "failed_units": sorted(failed_units, key=lambda item: item.get("unit_id", "")),
        "skipped_units": sorted(skipped_units),
        "output_dir": output_dir,
        "checkpoint_file": checkpoint_file,
    }
    if extra:
        manifest.update(extra)
    return manifest


def save_manifest(runtime_root: Path | str, manifest: Mapping[str, Any]) -> Path:
    path = manifest_path(runtime_root, manifest["provider"], manifest["dataset"], manifest["run_id"])
    atomic_write_json(path, dict(manifest))
    return path


def load_manifest(runtime_root: Path | str, provider: str, dataset: str, run_id: str) -> dict[str, Any] | None:
    path = manifest_path(runtime_root, provider, dataset, run_id)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
