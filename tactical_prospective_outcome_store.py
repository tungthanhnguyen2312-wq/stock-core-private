"""Session-sharded tactical outcomes; legacy compaction is disposable derived state.

Single writer. Readers only admit a shard through its sealed manifest. Limits
bound the explicit run index; no process-global outcome cache exists.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile

CONTRACT_VERSION = "tactical_prospective_shadow_outcome_store/v2"
LEGACY_CACHE_VERSION = "tactical_shadow_legacy_outcome_compaction/v1"
MAX_ROWS = 300_000
MAX_OBSERVATIONS = 50_000
MAX_ROW_BYTES = 8 * 1024 * 1024
MAX_LATEST_BYTES = 128 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024


def _error(code):
    from tactical_reversal_prospective_shadow_collection import ProspectiveShadowCollectionError
    return ProspectiveShadowCollectionError(code)


def _canon(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(path):
    digest, size = hashlib.sha256(), 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _rank(row):
    # V1 resolves equal evaluation sessions in sorted content-addressed filename
    # order. Preserve that tie-break across shard/legacy discovery order.
    return (str(row.get("evaluation_as_of_session")), hashlib.sha256(row["outcome_update_id"].encode("utf-8")).hexdigest())


def _valid(row):
    body = dict(row)
    identity = body.pop("outcome_update_id", None)
    return identity == "tactical_prospective_shadow_outcome:" + hashlib.sha256(_canon(body).encode("utf-8")).hexdigest()


def _atomic_json(path, payload):
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".manifest-", suffix=".tmp", delete=False) as out:
            temp = Path(out.name)
            out.write((_canon(payload) + "\n").encode("utf-8"))
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


class OutcomeShardWriter:
    def __init__(self, root, session, inputs):
        # A session must be a directory component, never a supplied path.
        from datetime import date
        if date.fromisoformat(session).isoformat() != session:
            raise _error("OUTCOME_SESSION_INVALID")
        self.directory = Path(root) / "outcome_sessions" / session
        self.directory.mkdir(parents=True, exist_ok=True)
        self.session, self.inputs = session, inputs
        self.count, self.size, self.digest = 0, 0, hashlib.sha256()
        self.file = tempfile.NamedTemporaryFile(dir=self.directory, prefix=".outcomes-", suffix=".tmp", delete=False)
        self.temp = Path(self.file.name)
        self.observation_digest = hashlib.sha256()

    def append(self, outcome):
        if not _valid(outcome) or outcome.get("evaluation_as_of_session") != self.session:
            raise _error("OUTCOME_CONTENT_IDENTITY_INVALID")
        data = (_canon(outcome) + "\n").encode("utf-8")
        if len(data) > MAX_ROW_BYTES or self.count >= MAX_ROWS:
            raise _error("OUTCOME_STORE_INDEX_LIMIT")
        self.file.write(data)
        self.digest.update(data)
        self.size += len(data)
        self.count += 1

    def record_observation(self, observation):
        self.observation_digest.update((_canon(observation) + "\n").encode("utf-8"))

    def promote(self):
        self.file.flush()
        os.fsync(self.file.fileno())
        self.file.close()
        manifest = {"contract_version": CONTRACT_VERSION, "evaluation_as_of_session": self.session,
                    "outcome_count": self.count, "shard": "outcomes.ndjson", "sha256": self.digest.hexdigest(),
                    "byte_count": self.size, "input_identities": {**self.inputs, "observations_sha256": self.observation_digest.hexdigest()}}
        path = self.directory / "manifest.json"
        shard = self.directory / "outcomes.ndjson"
        if path.exists():
            old = _read_manifest(path)
            if old != manifest or _digest(shard) != (manifest["sha256"], manifest["byte_count"]):
                raise _error("IMMUTABLE_OUTCOME_SESSION_CONFLICT")
            return
        # An orphan from a failed pre-manifest write is not retained evidence.
        os.replace(self.temp, shard)
        try:
            _atomic_json(path, manifest)
        except Exception:
            shard.unlink(missing_ok=True)
            raise

    def close(self):
        self.file.close()
        self.temp.unlink(missing_ok=True)


@contextmanager
def outcome_session_writer(root, session, inputs):
    writer = OutcomeShardWriter(root, session, inputs)
    try:
        yield writer
        writer.promote()
    finally:
        writer.close()


def _read_manifest(path):
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        raise _error("OUTCOME_MANIFEST_OVERSIZED")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise _error("OUTCOME_MANIFEST_INVALID")
    return value


def _legacy_compaction(root, metrics, legacy_root=None):
    originals = sorted(((legacy_root or root) / "outcome_updates").glob("*.json"))
    if len(originals) > MAX_ROWS:
        raise _error("OUTCOME_STORE_INDEX_LIMIT")
    if not originals:
        return None
    directory = root / "_derived_outcome_index"
    directory.mkdir(parents=True, exist_ok=True)
    shard, manifest_path = directory / "legacy.ndjson", directory / "manifest.json"
    candidate = None
    try:
        manifest = _read_manifest(manifest_path)
        if (manifest.get("contract_version") == LEGACY_CACHE_VERSION
                and manifest.get("outcome_count") == len(originals)
                and _digest(shard) == (manifest.get("sha256"), manifest.get("byte_count"))):
            candidate = manifest
    except (OSError, ValueError, TypeError):
        pass
    identity = None
    if candidate is not None:
        fingerprint = hashlib.sha256()
        for path in originals:
            before = path.stat()
            sha, size = _digest(path)
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise _error("LEGACY_OUTCOME_CHANGED_DURING_READ")
            fingerprint.update(_canon([path.name, sha, size]).encode("utf-8"))
            metrics["legacy_validation_files_opened"] += 1
            metrics["legacy_validation_bytes"] += size
        identity = fingerprint.hexdigest()
        if candidate.get("source_sha256") == identity:
            metrics["legacy_compaction_hits"] += 1
            return shard
    temp = None
    try:
        digest, size = hashlib.sha256(), 0
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".legacy-", suffix=".tmp", delete=False) as out:
            temp = Path(out.name)
            check = hashlib.sha256()
            for path in originals:
                before = path.stat()
                if before.st_size > MAX_ROW_BYTES:
                    raise _error("OUTCOME_ROW_OVERSIZED")
                with path.open("rb") as source:
                    data = source.read(MAX_ROW_BYTES + 1)
                after = path.stat()
                if len(data) > MAX_ROW_BYTES or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise _error("LEGACY_OUTCOME_CHANGED_DURING_READ")
                metrics["legacy_validation_files_opened"] += 1
                metrics["legacy_validation_bytes"] += len(data)
                check.update(_canon([path.name, hashlib.sha256(data).hexdigest(), len(data)]).encode("utf-8"))
                row = json.loads(data)
                metrics["legacy_json_parses"] += 1
                if not isinstance(row, dict) or not _valid(row):
                    raise _error("LEGACY_OUTCOME_CONTENT_IDENTITY_INVALID")
                line = (_canon(row) + "\n").encode("utf-8")
                out.write(line)
                digest.update(line)
                size += len(line)
            if identity is not None and check.hexdigest() != identity:
                raise _error("LEGACY_OUTCOME_CHANGED_DURING_READ")
            identity = check.hexdigest()
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, shard)
        _atomic_json(manifest_path, {"contract_version": LEGACY_CACHE_VERSION, "source_sha256": identity,
                                   "outcome_count": len(originals), "sha256": digest.hexdigest(), "byte_count": size})
        return shard
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


class OutcomeStoreIndex:
    """Bounded run-scoped lookup of exact row offsets plus each observation's latest.

    Legacy originals are byte-validated once per run, never trusted by stat alone.
    Warm discovery parses compact rows through a small number of streaming files.
    Historical per-observation reads seek directly to indexed rows.
    """
    def __init__(self, root, metrics=None, *, legacy_root=None):
        self.root = Path(root)
        legacy_root = Path(legacy_root) if legacy_root is not None else self.root
        self.metrics = metrics if metrics is not None else {}
        for key in ("legacy_validation_files_opened", "legacy_validation_bytes", "legacy_json_parses", "legacy_compaction_hits", "shard_files_opened", "shard_rows_parsed"):
            self.metrics.setdefault(key, 0)
        self.locations, self.latest = {}, {}
        seen, count, latest_bytes = set(), 0, 0
        latest_sizes = {}
        shards = []
        try:
            legacy = _legacy_compaction(self.root, self.metrics, legacy_root)
            if legacy is not None:
                shards.append((legacy, None))
        except OSError:
            # Derived-state write/read failure cannot hide original retained outcomes.
            originals = sorted((legacy_root / "outcome_updates").glob("*.json"))
            if len(originals) > MAX_ROWS:
                raise _error("OUTCOME_STORE_INDEX_LIMIT")
            shards.extend((path, "legacy") for path in originals)
        for path in sorted((self.root / "outcome_sessions").glob("*/manifest.json")):
            manifest = _read_manifest(path)
            shard = path.parent / "outcomes.ndjson"
            if (manifest.get("contract_version") != CONTRACT_VERSION or manifest.get("shard") != shard.name
                    or manifest.get("evaluation_as_of_session") != path.parent.name
                    or _digest(shard) != (manifest.get("sha256"), manifest.get("byte_count"))):
                raise _error("OUTCOME_SHARD_MANIFEST_INVALID")
            shards.append((shard, manifest))
        for path, manifest in shards:
            rows = 0
            self.metrics["shard_files_opened"] += 1
            with path.open("rb") as source:
                while True:
                    offset = source.tell()
                    line = source.read(MAX_ROW_BYTES + 1) if manifest == "legacy" else source.readline(MAX_ROW_BYTES + 1)
                    if len(line) > MAX_ROW_BYTES:
                        raise _error("OUTCOME_ROW_OVERSIZED")
                    if not line:
                        break
                    row = json.loads(line)
                    self.metrics["shard_rows_parsed"] += 1
                    if not isinstance(row, dict) or not _valid(row):
                        raise _error("OUTCOME_CONTENT_IDENTITY_INVALID")
                    if isinstance(manifest, dict) and row.get("evaluation_as_of_session") != manifest["evaluation_as_of_session"]:
                        raise _error("OUTCOME_SHARD_SESSION_INVALID")
                    rows += 1
                    count += 1
                    if count > MAX_ROWS:
                        raise _error("OUTCOME_STORE_INDEX_LIMIT")
                    identity = row["outcome_update_id"]
                    if identity in seen:
                        continue
                    seen.add(identity)
                    observation = row["observation_id"]
                    self.locations.setdefault(observation, []).append((path, offset, len(line)))
                    old = self.latest.get(observation)
                    if old is None or _rank(row) >= _rank(old):
                        latest_bytes += len(line) - latest_sizes.get(observation, 0)
                        latest_sizes[observation] = len(line)
                        if latest_bytes > MAX_LATEST_BYTES:
                            raise _error("OUTCOME_STORE_INDEX_LIMIT")
                        self.latest[observation] = row
                    if len(self.latest) > MAX_OBSERVATIONS:
                        raise _error("OUTCOME_STORE_INDEX_LIMIT")
            if isinstance(manifest, dict) and rows != manifest.get("outcome_count"):
                raise _error("OUTCOME_SHARD_COUNT_INVALID")

    def history(self, observation_id):
        rows = []
        for path, offset, length in self.locations.get(observation_id, []):
            with path.open("rb") as source:
                source.seek(offset)
                row = json.loads(source.read(length))
            if not _valid(row) or row.get("observation_id") != observation_id:
                raise _error("OUTCOME_INDEX_SOURCE_CHANGED")
            rows.append(row)
        return sorted(rows, key=_rank)
