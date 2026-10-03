"""Streaming, resource-bounded builder for ``prospective_decision_outcome_feedback/v3``.

OWNER_DAILY_FEEDBACK_RESOURCE_CONTAINMENT_V1. This is a resource corrective, not a learning-policy change:
every classification, horizon, maturity, ordering and identity rule is still owned by
``prospective_decision_outcome_feedback`` / ``integrated_decision_prospective_feedback`` /
``prospective_decision_retention``. This module only changes *how* the same artifact is read and written.

* Inputs stay on disk. T0 snapshots and legacy Integrated Decision artifacts are streamed one record at a
  time; the original immutable file remains the only authority (derived receipts/indexes are keyed by the
  SHA-256 of the exact source bytes and are rebuildable).
* Per-record feedback rows are written incrementally to spools, the canonical artifact identity is hashed
  incrementally, and the artifact is atomically published only after a raw-byte re-verification.
* The artifact content and ``artifact_identity`` are identical to ``build_feedback_artifact``'s; only the
  on-disk whitespace differs (canonical compact JSON instead of ``indent=2``).
"""
from __future__ import annotations

import errno
import hashlib
import heapq
import io
import json
import os
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

import bounded_artifact_stream as bas
import integrated_decision_prospective_feedback as forward_bridge
import prospective_decision_outcome_feedback as fb
import prospective_decision_retention as retention

STREAM_CONTRACT_VERSION = "prospective_feedback_stream/v1"
COMPLETION_CONTRACT_VERSION = "prospective_feedback_completion/v1"
RESULT_CONTRACT_VERSION = "prospective_feedback_result/v1"
STATE_DIR = Path("operations-review/prospective-decision-outcome-feedback-v1/_stream")
RECEIPT_MAX_BYTES = 64 * 1024 * 1024
ARTIFACT_IDENTITY_PREFIX = "prospective_decision_outcome_feedback:"
TEMP_PREFIX = ".feedback-"
LEGACY_UNSORTED_FALLBACK_MAX_BYTES = 128 * 1024 * 1024

OUTCOME_BUILT = "BUILT"
OUTCOME_ALREADY_COMPLETE = "ALREADY_COMPLETE"
OUTCOME_ALREADY_RETAINED_EQUAL = "ALREADY_RETAINED_EQUAL_IDENTITY"

REASON_SOURCE_INTEGRITY = "FEEDBACK_SOURCE_INTEGRITY_FAILED"
REASON_IMMUTABLE_CONFLICT = "FEEDBACK_IMMUTABLE_OUTPUT_CONFLICT"
REASON_COMPUTATION_ERROR = "FEEDBACK_COMPUTATION_ERROR"
REASON_RESOURCE_MEMORY = "FEEDBACK_RESOURCE_MEMORY_LIMIT"
REASON_RESOURCE_DISK = "FEEDBACK_RESOURCE_DISK_UNAVAILABLE"
REASON_INCOMPLETE_INPUT_CHANGED = "FEEDBACK_SOURCE_CHANGED_DURING_RUN"


class FeedbackStreamError(Exception):
    code = REASON_COMPUTATION_ERROR


class SourceIntegrityError(FeedbackStreamError):
    code = REASON_SOURCE_INTEGRITY


class ImmutableOutputConflict(FeedbackStreamError):
    code = REASON_IMMUTABLE_CONFLICT


def _canon_bytes(value: Any) -> bytes:
    return bas.canonical_bytes(value)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def code_digest() -> str:
    """Digest of every module whose behaviour defines the artifact; any change invalidates reuse."""
    names = ("prospective_decision_outcome_feedback", "integrated_decision_prospective_feedback",
             "prospective_decision_retention", "prospective_decision_outcome_measurement",
             "prospective_feedback_streaming", "bounded_artifact_stream", "session_bar_integrity",
             "fundamental_signal_consumption_contract", "governed_session_chain", "prospective_pit_capture_retention",
             "daily_session_level2_package")
    digest = hashlib.sha256()
    for name in names:
        module = __import__(name)
        path = Path(module.__file__)
        digest.update(name.encode() + b"\0" + hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).digest())
    return digest.hexdigest()


def _atomic_write_json(path: Path, value: Any, *, allow_nan: bool = True) -> None:
    """Best-effort derived state; never authoritative, never partially visible."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=allow_nan).encode("utf-8")
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=TEMP_PREFIX + "state-", suffix=".tmp", delete=False) as out:
            temporary = Path(out.name)
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _read_state_json(path: Path) -> dict[str, Any] | None:
    try:
        if path.stat().st_size > RECEIPT_MAX_BYTES:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None
    return value if isinstance(value, dict) else None


class _HashingBinary(io.RawIOBase):
    """Raw reader that hashes exactly the bytes handed to the JSON parser (no TOCTOU between proof and use)."""

    def __init__(self, path: Path):
        self._file = open(path, "rb", buffering=0)
        self.digest = hashlib.sha256()
        self.bytes_read = 0

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        count = self._file.readinto(buffer)
        if count:
            self.digest.update(memoryview(buffer)[:count])
            self.bytes_read += count
        return count

    def close(self) -> None:
        try:
            self._file.close()
        finally:
            super().close()

    def drain(self) -> None:
        while self.readinto(bytearray(1 << 20)):
            pass


class _HashedStream:
    """Context manager: text view over a hashing reader. ``finish()`` drains and returns (sha256, size)."""

    def __init__(self, path: Path):
        self.raw = _HashingBinary(path)
        self.text = io.TextIOWrapper(io.BufferedReader(self.raw, buffer_size=1 << 20), encoding="utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.text.close()
        return False

    def finish(self) -> tuple[str, int]:
        # Anything the parser did not request (trailing whitespace) is still part of the proven bytes.
        self.raw.drain()
        return self.raw.digest.hexdigest(), self.raw.bytes_read


class StreamedRecords:
    """Placeholder for a ``records`` container that stays on disk. Supports ``len``/truthiness only."""

    def __init__(self, path: Path, count: int, kind: str):
        self.path, self.count, self.kind = Path(path), int(count), kind

    def __len__(self) -> int:
        return self.count

    def __bool__(self) -> bool:
        return self.count > 0

    def __iter__(self):  # an accidental full materialisation must fail loudly, not silently load
        raise TypeError("STREAMED_RECORDS_REQUIRE_EXPLICIT_STREAMING")

    def items(self):
        raise TypeError("STREAMED_RECORDS_REQUIRE_EXPLICIT_STREAMING")


class SourceHandle(dict):
    """Header (every non-record member) plus bookkeeping for one streamed source file."""
    valid = True
    raw_sha256 = None
    size = None
    path = None
    t0_prices: Mapping[str, Any] | None = None


def _metric(metrics: dict[str, Any] | None, key: str, amount: int | float = 1) -> None:
    if metrics is not None:
        metrics[key] = metrics.get(key, 0) + amount


# --------------------------------------------------------------------------------------------------
# Legacy Integrated Decision artifacts (header scan + record stream)
# --------------------------------------------------------------------------------------------------

def _legacy_receipt_path(state_root: Path, raw_sha: str) -> Path:
    return state_root / STATE_DIR / "legacy_receipts" / (raw_sha + ".json")


def scan_legacy_artifact(path: Path, metrics: dict[str, Any] | None = None, state_root: Path | None = None) -> SourceHandle | None:
    """Header-only pass (``records`` are decoded and discarded). ``None`` mirrors ``_load_json`` failures.

    With ``state_root`` the header and record count are cached under the SHA-256 of the exact bytes, so an
    unchanged multi-hundred-MB legacy artifact is hashed (fast) but not decoded again for its header.
    """
    header: dict[str, Any] = {}
    count = 0
    if state_root is not None:
        try:
            raw = bas.source_hash(path)
            size_now = path.stat().st_size
        except OSError:
            return None
        _metric(metrics, "stream_sha256_bytes", size_now)
        cached = _read_state_json(_legacy_receipt_path(state_root, raw))
        if (cached and cached.get("contract_version") == STREAM_CONTRACT_VERSION and cached.get("source_sha256") == raw
                and cached.get("size") == size_now and isinstance(cached.get("header"), dict) and isinstance(cached.get("record_count"), int)):
            handle = SourceHandle(cached["header"])
            handle["records"] = StreamedRecords(path, cached["record_count"], "legacy")
            handle.valid, handle.raw_sha256, handle.size, handle.path = True, raw, size_now, Path(path)
            _metric(metrics, "legacy_receipt_hits")
            return handle
    try:
        with _HashedStream(path) as stream:
            parser = bas.ObjectStream(stream.text, sorted_required=False)
            for key in parser.members():
                if key == "records":
                    for _ticker in parser.members():
                        parser.value()
                        count += 1
                else:
                    header[key] = parser.value()
            if parser.peek():
                return None
            digest, size = stream.finish()
    except (OSError, UnicodeError, ValueError):
        return None
    _metric(metrics, "stream_header_scan_bytes", size)
    handle = SourceHandle(header)
    handle.update({"records": StreamedRecords(path, count, "legacy")})
    handle.valid, handle.raw_sha256, handle.size, handle.path = True, digest, size, Path(path)
    if state_root is not None and digest == raw and size == size_now:
        try:
            _atomic_write_json(_legacy_receipt_path(state_root, digest), {
                "contract_version": STREAM_CONTRACT_VERSION, "source_sha256": digest, "size": size, "header": header, "record_count": count})
        except (OSError, ValueError):
            pass
    return handle


def iter_legacy_records(handle: SourceHandle) -> Iterator[tuple[str, Any]]:
    """Yield ``(ticker, decision)`` in file order, proving the exact bytes equal the header-scan hash."""
    expected_sha, expected_size, expected_count = handle.raw_sha256, handle.size, len(handle["records"])
    seen = 0
    with _HashedStream(handle.path) as stream:
        parser = bas.ObjectStream(stream.text, sorted_required=False)
        for key in parser.members():
            if key == "records":
                previous = None
                for ticker in parser.members():
                    if previous is not None and ticker <= previous:
                        raise FeedbackStreamError("LEGACY_RECORDS_NOT_SORTED_FOR_STREAMING:" + str(handle.path))
                    previous = ticker
                    seen += 1
                    yield ticker, parser.value()
            else:
                parser.value()
        digest, size = stream.finish()
    if digest != expected_sha or size != expected_size or seen != expected_count:
        raise SourceIntegrityError(REASON_INCOMPLETE_INPUT_CHANGED + ":" + str(handle.path))


# --------------------------------------------------------------------------------------------------
# Immutable T0 snapshots: streamed identity proof + receipt cache
# --------------------------------------------------------------------------------------------------

def _receipt_path(state_root: Path, raw_sha: str) -> Path:
    return state_root / STATE_DIR / "t0_receipts" / (raw_sha + ".json")


def _verify_snapshot_stream(path: Path) -> dict[str, Any]:
    """Cryptographically equivalent to ``retention.validate_snapshot`` without materialising the snapshot."""
    state = {"valid": True, "reason": None}
    t0_candidates: dict[str, Any] = {}

    def on_record(ticker, row):
        if not state["valid"]:
            return
        if not isinstance(row, Mapping) or row.get("ticker") != ticker:
            state.update(valid=False, reason="RECORD_TICKER_MISMATCH")
            return
        body = {k: v for k, v in row.items() if k != "prospective_snapshot_record_identity"}
        if row.get("prospective_snapshot_record_identity") != retention.RECORD_PREFIX + _sha256_bytes(_canon_bytes(body)):
            state.update(valid=False, reason="RECORD_IDENTITY_MISMATCH")
            return
        observation = row.get("t0_close_observation")
        if isinstance(observation, Mapping):
            t0_candidates[ticker] = dict(observation)

    metadata, digest, count = bas.stream_artifact(path, excluded={"snapshot_identity"}, on_record=on_record)
    if metadata.get("snapshot_identity") != retention.SNAPSHOT_PREFIX + digest:
        state.update(valid=False, reason="SNAPSHOT_IDENTITY_MISMATCH")
    if metadata.get("contract_version") != retention.CONTRACT_VERSION:
        state.update(valid=False, reason="SNAPSHOT_CONTRACT_MISMATCH")
    session = metadata.get("session")
    t0_prices = {t: row for t, row in t0_candidates.items() if isinstance(session, str) and row.get("session") == session}
    return {"header": metadata, "record_count": count, "valid": state["valid"], "reason": state["reason"], "t0_prices": t0_prices}


def load_snapshot_handle(path: Path, state_root: Path, metrics: dict[str, Any] | None = None) -> SourceHandle | None:
    """Loader seam for ``retention.discover_snapshots``; ``None`` mirrors an unreadable file."""
    try:
        raw_sha = bas.source_hash(path)
        size = path.stat().st_size
    except OSError:
        return None
    _metric(metrics, "stream_sha256_bytes", size)
    receipt_file = _receipt_path(state_root, raw_sha)
    receipt = _read_state_json(receipt_file)
    if not (receipt and receipt.get("contract_version") == STREAM_CONTRACT_VERSION and receipt.get("source_sha256") == raw_sha
            and receipt.get("size") == size and receipt.get("code_digest") == _verification_code_digest()):
        receipt = None
    if receipt is None:
        try:
            proof = _verify_snapshot_stream(path)
        except (OSError, UnicodeError):
            return None
        except ValueError:
            # Not canonical sorted JSON. The original loader accepted such a file when it still hashed
            # to its identity; keep that for small files, otherwise treat it as unreadable.
            if size > LEGACY_UNSORTED_FALLBACK_MAX_BYTES:
                return None
            snapshot = retention._load(path)
            if not snapshot:
                return None
            records = snapshot.get("records") or {}
            proof = {"header": {k: v for k, v in snapshot.items() if k != "records"}, "record_count": len(records),
                     "valid": retention.validate_snapshot(snapshot), "reason": None,
                     "t0_prices": {t: dict(r["t0_close_observation"]) for t, r in records.items()
                                   if isinstance(r, Mapping) and isinstance(r.get("t0_close_observation"), Mapping)
                                   and r["t0_close_observation"].get("session") == snapshot.get("session")}}
        receipt = {"contract_version": STREAM_CONTRACT_VERSION, "source_sha256": raw_sha, "size": size,
                   "code_digest": _verification_code_digest(), **proof}
        _metric(metrics, "stream_verified_bytes", size)
        _metric(metrics, "t0_receipt_misses")
        try:
            _atomic_write_json(receipt_file, receipt)
        except OSError:
            pass
    else:
        _metric(metrics, "t0_receipt_hits")
    handle = SourceHandle(receipt["header"])
    handle["records"] = StreamedRecords(path, receipt["record_count"], "t0")
    handle.valid, handle.raw_sha256, handle.size, handle.path = bool(receipt["valid"]), raw_sha, size, Path(path)
    handle.t0_prices = receipt["t0_prices"]
    return handle


_VERIFICATION_DIGEST: str | None = None


def _verification_code_digest() -> str:
    global _VERIFICATION_DIGEST
    if _VERIFICATION_DIGEST is None:
        digest = hashlib.sha256()
        for name in ("prospective_decision_retention", "bounded_artifact_stream", "prospective_feedback_streaming"):
            module = __import__(name)
            digest.update(hashlib.sha256(Path(module.__file__).read_bytes().replace(b"\r\n", b"\n")).digest())
        _VERIFICATION_DIGEST = digest.hexdigest()
    return _VERIFICATION_DIGEST


def iter_snapshot_records(handle: SourceHandle) -> Iterator[tuple[str, Any]]:
    """Yield ``(ticker, retained_record)`` in sorted order, proving the exact bytes equal the verified hash."""
    expected_sha, expected_size, expected_count = handle.raw_sha256, handle.size, len(handle["records"])
    seen = 0
    with _HashedStream(handle.path) as stream:
        parser = bas.ObjectStream(stream.text, sorted_required=False)
        for key in parser.members():
            if key == "records":
                previous = None
                for ticker in parser.members():
                    if previous is not None and ticker <= previous:
                        raise FeedbackStreamError("T0_RECORDS_NOT_SORTED_FOR_STREAMING:" + str(handle.path))
                    previous = ticker
                    seen += 1
                    yield ticker, parser.value()
            else:
                parser.value()
        digest, size = stream.finish()
    if digest != expected_sha or size != expected_size or seen != expected_count:
        raise SourceIntegrityError(REASON_INCOMPLETE_INPUT_CHANGED + ":" + str(handle.path))


# --------------------------------------------------------------------------------------------------
# Exact-session price snapshots: compact, same-session-only observation index
# --------------------------------------------------------------------------------------------------

class PriceIndex:
    """Compact stand-in for the P3F9B exact-session snapshots the forward bridge reads.

    ``retained_session_price_observations`` and ``evaluate_serialized_close_condition`` only ever consume
    the observation(s) whose ``session`` equals the snapshot's own expected session, so that subset (all
    matches, so the ``len(matches) != 1`` rule is preserved) is exactly sufficient.
    """

    def __init__(self, state_root: Path, metrics: dict[str, Any] | None = None):
        self.state_root, self.metrics = Path(state_root), metrics
        self.sources: dict[str, dict[str, Any]] = {}
        self._content_hash: dict[str, str] = {}

    def _file(self, session: str, raw_sha: str) -> Path:
        return self.state_root / STATE_DIR / "price_index" / f"{session}-{raw_sha[:32]}.json"

    def load(self, path: Path, session: str) -> dict[str, Any] | None:
        try:
            raw_sha = bas.source_hash(path)
            size = path.stat().st_size
        except OSError:
            return None
        _metric(self.metrics, "stream_sha256_bytes", size)
        cached = _read_state_json(self._file(session, raw_sha))
        if cached and cached.get("contract_version") == STREAM_CONTRACT_VERSION and cached.get("source_sha256") == raw_sha \
                and cached.get("session") == session and cached.get("size") == size:
            _metric(self.metrics, "price_index_hits")
            snapshot = cached["snapshot"]
        else:
            snapshot = self._build(path, session)
            _metric(self.metrics, "price_index_misses")
            _metric(self.metrics, "stream_parsed_bytes", size)
            if snapshot is not None:
                try:
                    _atomic_write_json(self._file(session, raw_sha), {
                        "contract_version": STREAM_CONTRACT_VERSION, "source_sha256": raw_sha, "size": size,
                        "session": session, "snapshot": snapshot}, allow_nan=True)
                except OSError:
                    pass
        self.sources[session] = {"path": Path(path), "raw_sha256": raw_sha, "size": size}
        return snapshot

    def _build(self, path: Path, session: str) -> dict[str, Any] | None:
        header: dict[str, Any] = {}
        records: dict[str, Any] = {}
        try:
            with _HashedStream(path) as stream:
                parser = bas.ObjectStream(stream.text, sorted_required=False)
                for key in parser.members():
                    if key == "records":
                        for ticker in parser.members():
                            row = parser.value()
                            record = row if isinstance(row, Mapping) else {}
                            observations = [o for o in (record.get("observations") or [])
                                            if isinstance(o, Mapping) and o.get("session") == session]
                            records[ticker] = {"observations": observations}
                    else:
                        header[key] = parser.value()
                if parser.peek():
                    return None
                stream.finish()
        except (OSError, UnicodeError, ValueError):
            return None
        if header.get("resolved_completed_session") != session or not isinstance(header.get("snapshot_identity"), str):
            return None
        return {"resolved_completed_session": header["resolved_completed_session"],
                "snapshot_identity": header["snapshot_identity"], "records": records}

    def content_hash(self, session: str) -> str:
        """Hash of the *complete* source snapshot (only needed for terminal settled-cache proofs)."""
        if session in self._content_hash:
            return self._content_hash[session]
        source = self.sources[session]
        cache_file = self._file(session, source["raw_sha256"])
        cached = _read_state_json(cache_file) or {}
        if cached.get("content_sha256"):
            self._content_hash[session] = cached["content_sha256"]
            return cached["content_sha256"]
        _meta, digest, _count = bas.stream_artifact(source["path"], excluded=set(), on_record=lambda t, r: None)
        if cached:
            cached["content_sha256"] = digest
            try:
                _atomic_write_json(cache_file, cached, allow_nan=True)
            except OSError:
                pass
        self._content_hash[session] = digest
        return digest


class _StreamSettledCache(fb.SettledFeedbackCache):
    """Existing terminal-only cache; only the snapshot content proof is sourced from the file, not a resident object."""

    def __init__(self, *args, content_hash: Callable[[str, Any], str], **kwargs):
        self._external_content_hash = content_hash
        super().__init__(*args, **kwargs)

    def _snapshot_content_hash(self, session, snapshot):
        return self._external_content_hash(session, snapshot)


# --------------------------------------------------------------------------------------------------
# Aggregation: reduced rows fed to the *original* summary / health functions (parity by construction)
# --------------------------------------------------------------------------------------------------

class _Aggregator:
    def __init__(self):
        self.by_posture: dict[str, list] = defaultdict(list)
        self.by_coherence: dict[str, list] = defaultdict(list)
        self.by_axis: dict[str, list] = defaultdict(list)
        self.false_negatives: list = []
        self.failed_setups: list = []
        self.horizon_coverage: dict[str, Counter] = {name: Counter() for name in forward_bridge.FORWARD_HORIZONS}
        self.required: dict[str, list] = {ticker: [] for ticker in fb.REQUIRED_TICKERS}
        self.health_rows: list = []
        self.tickers: set[str] = set()
        self.count = 0
        self.t5_mature = 0

    def add(self, row: Mapping[str, Any]) -> None:
        self.count += 1
        horizons = row["forward_outcomes"]["horizons"]
        h5 = horizons.get("forward_close_return_5")
        excursion5 = (row["forward_outcomes"].get("close_path_by_horizon") or {}).get("close_excursion_5")
        mini: dict[str, Any] = {"fundamental_decision_policy_version": row.get("fundamental_decision_policy_version"),
                                "forward_outcomes": {"horizons": {}, "close_path_by_horizon": {}}}
        if h5 is not None:
            mini["forward_outcomes"]["horizons"]["forward_close_return_5"] = {"status": h5.get("status"), "return": h5.get("return")}
        if excursion5 is not None:
            mini["forward_outcomes"]["close_path_by_horizon"]["close_excursion_5"] = {
                key: excursion5.get(key) for key in ("status", "CLOSE_MFE", "CLOSE_MAE") if key in excursion5}
        self.by_posture[str(row["research_action_posture"])].append(mini)
        self.by_coherence[str(row["coherence_state"])].append(mini)
        axes = row["evidence_axes"]
        if axes["status"] == fb.FIELD_NOT_RETAINED:
            self.by_axis[fb.FIELD_NOT_RETAINED].append(mini)
        else:
            for name, axis in axes["axis_states"].items():
                self.by_axis[name + ":" + str(axis.get("state"))].append(mini)
        self.false_negatives.extend(fb._false_negatives([row]))
        self.failed_setups.extend(fb._failed_setups([row]))
        for name in forward_bridge.FORWARD_HORIZONS:
            self.horizon_coverage[name][horizons[name]["status"]] += 1
        if row["ticker"] in self.required:
            self.required[row["ticker"]].append(row)
        if horizons["forward_close_return_5"]["status"] == forward_bridge.MATURE:
            self.t5_mature += 1
        self.tickers.add(row["ticker"])
        trigger_condition = ((row.get("trigger") or {}).get("condition") or {})
        invalidation_condition = ((row.get("invalidation") or {}).get("condition") or {})
        self.health_rows.append({
            "temporal_qualification": {"status": (row.get("temporal_qualification") or {}).get("status")},
            "ticker": row.get("ticker"), "decision_session": row.get("decision_session"),
            "decision_identity": row.get("decision_identity"), "t0_snapshot_identity": row.get("t0_snapshot_identity"),
            "forward_outcomes": {"horizons": {name: {k: h.get(k) for k in ("series_fitness", "status", "maturation_state", "future_session")}
                                              for name, h in horizons.items() if isinstance(h, Mapping)}},
            "evidence_axes": {"status": (row.get("evidence_axes") or {}).get("status", fb.FIELD_NOT_RETAINED)},
            "trigger": {"condition": {"status": trigger_condition["status"]} if "status" in trigger_condition else {}},
            "invalidation": {"condition": {"status": invalidation_condition["status"]} if "status" in invalidation_condition else {}},
        })


# --------------------------------------------------------------------------------------------------
# Spooled artifact writer
# --------------------------------------------------------------------------------------------------

class _Spool:
    """Comma-joined canonical compact JSON elements (the exact bytes of a JSON array body)."""

    def __init__(self, directory: Path, name: str):
        self.path = directory / (TEMP_PREFIX + name + ".spool")
        self.file = open(self.path, "wb", buffering=1 << 20)
        self.count = 0

    def append(self, value: Any) -> None:
        if self.count:
            self.file.write(b",")
        self.file.write(_canon_bytes(value))
        self.count += 1

    def close(self) -> None:
        self.file.flush()
        self.file.close()

    def remove(self) -> None:
        try:
            self.file.close()
        except OSError:
            pass
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass


def _copy_hashing(source: Path, sinks: list[Callable[[bytes], Any]]) -> int:
    total = 0
    with open(source, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            total += len(block)
            for sink in sinks:
                sink(block)
    return total


def _identity_from_header(path: Path) -> str | None:
    """``artifact_identity`` is the first sorted key of both the legacy and the streamed layouts."""
    try:
        with open(path, "rb") as handle:
            head = handle.read(4096).decode("utf-8", errors="replace")
    except OSError:
        return None
    marker = '"artifact_identity":'
    index = head.find(marker)
    if index < 0:
        return None
    rest = head[index + len(marker):].lstrip()
    if not rest.startswith('"'):
        return None
    end = rest.find('"', 1)
    return rest[1:end] if end > 0 else None


def completion_manifest_path(output: Path) -> Path:
    return output.with_name(output.name + ".complete.json")


def read_completion(output: Path) -> dict[str, Any] | None:
    """A COMPLETE output has a matching manifest whose size and raw hash equal the artifact's current bytes."""
    manifest = _read_state_json(completion_manifest_path(output))
    if not manifest or manifest.get("contract_version") != COMPLETION_CONTRACT_VERSION:
        return None
    try:
        if output.stat().st_size != manifest.get("artifact_size"):
            return None
        if bas.source_hash(output) != manifest.get("artifact_raw_sha256"):
            return None
    except OSError:
        return None
    return manifest


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
        finally:
            kernel.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def cleanup_incomplete(directory: Path, *, older_than_seconds: float, now: float | None = None) -> list[str]:
    """Remove only this module's own temporaries: those of a dead writer immediately, others once stale."""
    removed = []
    now = time.time() if now is None else now
    try:
        entries = list(directory.iterdir())
    except OSError:
        return removed
    for entry in entries:
        if entry.name.startswith(TEMP_PREFIX) and entry.suffix in {".spool", ".tmp", ".incomplete"}:
            try:
                stem_pid = entry.stem.rsplit("-", 1)[-1]
                dead = stem_pid.isdigit() and int(stem_pid) != os.getpid() and not _pid_alive(int(stem_pid))
                if dead or now - entry.stat().st_mtime >= older_than_seconds:
                    entry.unlink()
                    removed.append(entry.name)
            except OSError:
                continue
    return removed


# --------------------------------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------------------------------

def _completed_chain(repository: Path) -> list[str]:
    operations = fb._operation_manifests(repository)
    qualified = []
    for link in fb._handoff_bundles(repository, operations):
        manifest = (link.get("operation") or {}).get("manifest") or {}
        if (link["producer_completed"] and link["resolved_completed_session"] == link["session"] and
                manifest.get("market_session") == link["session"] and manifest.get("generation_context") == fb._GENUINE_CONTEXT):
            qualified.append(link["session"])
    return sorted(set(qualified))


def _json_file_digest(path: Path) -> str | None:
    try:
        return bas.source_hash(path)
    except OSError:
        return None


def _future_chain_inputs(repository: Path, marker: Mapping[str, Any] | None, as_of: str) -> dict[str, Any]:
    """Conservative identity of everything ``load_chain`` reads; includes the as-of *date* only."""
    if not marker:
        return {"marker": None}
    import prospective_pit_capture_retention as store
    base = repository / store.STORE
    files = sorted((base / "sessions").glob("*.json")) if (base / "sessions").is_dir() else []
    calendar_files = []
    try:
        calendar_files = [p for p in sorted(base.rglob("*.json")) if "calendar" in str(p).lower()]
    except OSError:
        pass
    return {"marker": marker, "as_of_date": as_of[:10],
            "capture_sessions": {p.name: _json_file_digest(p) for p in files},
            "calendar_files": {str(p.relative_to(base)).replace("\\", "/"): _json_file_digest(p) for p in calendar_files}}


def build_streaming_feedback(root: str | Path, output: str | Path, *, state_root: str | Path | None = None,
                             metrics: dict[str, Any] | None = None, prior_summary: Mapping[str, Any] | None = None,
                             stale_temp_seconds: float = 6 * 3600) -> dict[str, Any]:
    """Build (or reuse) one feedback artifact. Returns a small structured result; never returns the artifact."""
    root, output = Path(root), Path(output)
    state_root = Path(state_root) if state_root is not None else root
    metrics = metrics if metrics is not None else {}
    clock = time.perf_counter
    phases: dict[str, float] = {}
    started = clock()
    output.parent.mkdir(parents=True, exist_ok=True)
    cleanup_incomplete(output.parent, older_than_seconds=stale_temp_seconds)

    # -- Phase 1: discovery (headers/proofs only; no record payload is resident) ---------------------
    t = clock()
    corpus = fb.discover_prospective_corpus(
        root, payload_projection=lambda artifact: artifact, use_summary_cache=True, cache_metrics=metrics,
        artifact_loader=lambda path, m: scan_legacy_artifact(path, m, state_root), cache_root=state_root)
    modern_discovery = retention.discover_snapshots(
        root, payload_projection=lambda snapshot: snapshot,
        snapshot_loader=lambda path: load_snapshot_handle(path, state_root, metrics),
        snapshot_validator=lambda snapshot: bool(snapshot.valid))
    modern_genuine = modern_discovery["genuine_snapshots"]
    modern_chain = sorted({row["snapshot"].get("session") for row in modern_genuine if isinstance(row["snapshot"].get("session"), str)})
    # Same selection as the original: the first genuine snapshot of a session supplies its sealed T0 closes.
    modern_prices: dict[str, dict[str, Any]] = {}
    for candidate in modern_genuine:
        snapshot = candidate["snapshot"]
        session = snapshot.get("session")
        if not isinstance(session, str) or session in modern_prices:
            continue
        records = {ticker: {"observations": [dict(row)]} for ticker, row in (snapshot.t0_prices or {}).items()}
        modern_prices[session] = {"resolved_completed_session": session,
                                  "snapshot_identity": ((snapshot.get("t0_price_snapshot") or {}).get("snapshot_identity")),
                                  "records": records}
    legacy_chain = corpus["qualified_session_chain"]
    completed_chain = _completed_chain(root)
    chain = sorted(set(completed_chain) | set(legacy_chain) | set(modern_chain))
    phases["discovery_s"] = clock() - t

    t = clock()
    prices = PriceIndex(state_root, metrics)
    snapshots: dict[str, Any] = {}
    for session in sorted(set(completed_chain) | set(legacy_chain)):
        if session in modern_prices:
            continue  # modern T0-sealed closes take precedence, exactly as {**completed, **legacy, **modern}
        loaded = prices.load(fb.level2.session_artifact_paths(root, session)["exact_session_snapshot"], session)
        if loaded is not None:
            snapshots[session] = loaded
    snapshots.update(modern_prices)
    phases["price_index_s"] = clock() - t

    from prospective_pit_capture_retention import load_marker, load_chain, io_known_at
    marker = load_marker(root)
    as_of = io_known_at()
    future_chain = load_chain(root, as_of=as_of) if marker else None

    def content_hash(session, snapshot):
        if session in prices.sources:
            return prices.content_hash(session)
        return retention._hash(snapshot)  # modern-derived object is small and was hashed by value originally

    settled = _StreamSettledCache(state_root, chain, snapshots, enabled=True, metrics=metrics, content_hash=content_hash)
    future_settled = _StreamSettledCache(state_root, future_chain, snapshots, enabled=False, metrics=metrics,
                                         content_hash=content_hash) if marker else None

    # -- Input identity (cheap: hashes already taken during discovery) --------------------------------
    code = code_digest()
    input_manifest = {
        "contracts": {"feedback": fb.CONTRACT_VERSION, "forward": forward_bridge.CONTRACT_VERSION,
                      "retention": retention.CONTRACT_VERSION, "temporal": fb.TEMPORAL_CONTRACT_VERSION,
                      "policy": fb.OUTCOME_POLICY_CONSTANTS, "horizons": forward_bridge.FORWARD_HORIZONS},
        "chain": chain,
        "t0_snapshots": sorted([[str(c["snapshot"].get("snapshot_identity")), c["snapshot"].raw_sha256, c["snapshot"].size]
                                for c in modern_genuine]),
        "snapshot_inventory": [[r.get("snapshot_identity"), r.get("classification")] for r in modern_discovery["inventory"]],
        "legacy_artifacts": sorted([[c["artifact_path"], c["artifact"].raw_sha256, c["artifact"].size] for c in corpus["genuine_artifacts"]]),
        "artifact_inventory": [[r["artifact_path"], r["artifact_identity"], r["classification"], r["record_count"]] for r in corpus["inventory"]],
        "handoff_inventory": modern_discovery["handoff_snapshot_inventory"],
        "price_sources": {s: [v["raw_sha256"], v["size"]] for s, v in sorted(prices.sources.items())},
        "modern_price_sessions": sorted(modern_prices),
        "future_chain": _future_chain_inputs(root, marker, as_of),
    }
    # Data identity only: the same retained inputs keep the same digest across code changes, so FEEDBACK_CALL_RELATION
    # reports what the *evidence* did. Reuse additionally requires an identical code digest (below).
    input_digest = _sha256_bytes(_canon_bytes(input_manifest))
    inputs_summary = {"chain_sessions": chain, "t0_snapshot_identities": sorted(r[0] for r in input_manifest["t0_snapshots"]),
                      "legacy_artifact_paths": sorted(r[0] for r in input_manifest["legacy_artifacts"]),
                      "artifact_inventory_paths": sorted(r[0] for r in input_manifest["artifact_inventory"]),
                      "input_digest": input_digest}
    relation = relate(prior_summary, inputs_summary)

    # -- Terminal reuse -----------------------------------------------------------------------------
    existing = read_completion(output)
    if existing and existing.get("input_digest") == input_digest and existing.get("code_digest") == code:
        phases["total_s"] = clock() - started
        return _result(OUTCOME_ALREADY_COMPLETE, output, existing, inputs_summary, relation, metrics, phases)

    # -- Phase 2: stream rows -> spools, aggregate, then assemble ------------------------------------
    t = clock()
    sources_by_session = _sources_by_session(modern_genuine, corpus["genuine_artifacts"])
    spool_rows = _Spool(output.parent, f"{output.name}-rows-{os.getpid()}")
    spool_trigger = _Spool(output.parent, f"{output.name}-trigger-{os.getpid()}")
    final_tmp = output.parent / (TEMP_PREFIX + output.name + f"-{os.getpid()}.incomplete")
    aggregate = _Aggregator()
    try:
        for row in _iter_rows(sources_by_session, settled, future_settled, marker):
            spool_rows.append(row)
            spool_trigger.append(row["trigger_invalidation_outcome"] | {"feedback_identity": row["feedback_identity"], "ticker": row["ticker"]})
            aggregate.add(row)
            _metric(metrics, "rows")
        spool_rows.close()
        spool_trigger.close()
        phases["evaluate_s"] = clock() - t
        settled.finish()
        t = clock()
        sections = _sections(corpus, modern_discovery, modern_genuine, legacy_chain, modern_chain, chain,
                             snapshots_sessions=sorted(set(k for k in snapshots if k in legacy_chain) | set(modern_prices)),
                             aggregate=aggregate)
        identity, size, raw_sha, record_count = _assemble(final_tmp, sections, spool_rows, spool_trigger, metrics)
        phases["assemble_s"] = clock() - t
        outcome = _publish(final_tmp, output, identity, size, raw_sha, aggregate.count, input_digest, code, inputs_summary)
    finally:
        spool_rows.remove()
        spool_trigger.remove()
        try:
            final_tmp.unlink(missing_ok=True)
        except OSError:
            pass
    phases["total_s"] = clock() - started
    manifest = read_completion(output)
    if manifest is None:
        # An equal-identity artifact written by the original builder has no manifest; adopt it after proof.
        manifest = _adopt_existing(output, identity, size, raw_sha, aggregate.count, input_digest, code, inputs_summary)
    return _result(outcome, output, manifest, inputs_summary, relation, metrics, phases)


def relate(prior: Mapping[str, Any] | None, current: Mapping[str, Any]) -> dict[str, Any]:
    """FEEDBACK_CALL_RELATION from deterministic input identities (never from timing)."""
    if not prior:
        return {"relation": "NO_PRIOR", "new_sessions": [], "new_t0_snapshots": []}
    if prior.get("input_digest") == current.get("input_digest"):
        return {"relation": "IDENTICAL", "new_sessions": [], "new_t0_snapshots": []}
    new_sessions = sorted(set(current["chain_sessions"]) - set(prior["chain_sessions"]))
    new_t0 = sorted(set(current["t0_snapshot_identities"]) - set(prior["t0_snapshot_identities"]))
    superset = (set(prior["chain_sessions"]) <= set(current["chain_sessions"]) and
                set(prior["t0_snapshot_identities"]) <= set(current["t0_snapshot_identities"]) and
                set(prior["legacy_artifact_paths"]) <= set(current["legacy_artifact_paths"]))
    return {"relation": "INCREMENTAL" if superset else "DISTINCT", "new_sessions": new_sessions, "new_t0_snapshots": new_t0,
            "inventory_only_delta": sorted(set(current["artifact_inventory_paths"]) - set(prior["artifact_inventory_paths"]))}


def _sources_by_session(modern_genuine, legacy_genuine) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in modern_genuine:
        snapshot = candidate["snapshot"]
        grouped[str(snapshot.get("session"))].append({"kind": "modern", "candidate": candidate})
    for candidate in legacy_genuine:
        grouped[str(candidate["artifact"].get("session"))].append({"kind": "legacy", "candidate": candidate})
    return grouped


def _iter_rows(sources_by_session, settled, future_settled, marker) -> Iterator[dict[str, Any]]:
    for session in sorted(sources_by_session):
        streams = [_source_stream(index, source) for index, source in enumerate(sources_by_session[session])]
        for _ticker, _identity, _index, work in heapq.merge(*streams, key=lambda item: (item[0], item[1])):
            evaluator_choice, kwargs = work
            evaluator = future_settled if evaluator_choice(marker) else settled
            yield evaluator.evaluate(**kwargs)


def _source_stream(index: int, source: Mapping[str, Any]) -> Iterator[tuple[str, str, int, Any]]:
    candidate = source["candidate"]
    if source["kind"] == "modern":
        handle = candidate["snapshot"]
        inventory = candidate["inventory"]
        origin = handle.get("source_integrated_decision_artifact") or {}
        artifact = {"session": handle.get("session"), "artifact_identity": origin.get("artifact_identity"),
                    "contract_version": origin.get("contract_version", fb.FIELD_NOT_RETAINED), "requested_at": None}
        temporal = {
            "contract_version": fb.TEMPORAL_CONTRACT_VERSION, "status": fb.GENUINE, "decision_session": handle.get("session"),
            "decision_artifact_identity": origin.get("artifact_identity"),
            "daily_session_operation_identity": handle.get("daily_session_operation_identity"),
            "canonical_handoff_path": inventory.get("canonical_handoff_path"),
            "operation_manifest_path": inventory.get("operation_manifest_path"),
            "proof_reason_codes": inventory.get("proof_reason_codes"),
        }
        header = {k: v for k, v in handle.items() if k != "records"}
        for ticker, retained in iter_snapshot_records(handle):
            if not isinstance(retained, Mapping):
                continue
            projected_record = {**{k: v for k, v in retained.items() if k != "integrated_decision_at_t0"},
                                "integrated_decision_at_t0": fb._project_decision_for_feedback(retained["integrated_decision_at_t0"])}
            decision = projected_record.get("integrated_decision_at_t0")
            if not isinstance(decision, Mapping) or decision.get("ticker") != ticker:
                continue
            yield ticker, str(decision.get("decision_identity")), index, (
                lambda marker, a=artifact: bool(marker) and a["session"] >= marker["session"],
                {"artifact": artifact, "source_path": inventory["snapshot_path"], "temporal": temporal, "record": decision,
                 "t0_snapshot": header, "t0_snapshot_record": projected_record})
    else:
        handle = candidate["artifact"]
        header = {k: v for k, v in handle.items() if k != "records"}
        for ticker, decision in iter_legacy_records(handle):
            if not isinstance(decision, Mapping) or decision.get("ticker") != ticker:
                continue
            projected = fb._project_decision_for_feedback(decision)
            yield ticker, str(projected.get("decision_identity")), index, (
                lambda marker, a=header: bool(marker) and a["session"] >= marker["session"],
                {"artifact": header, "source_path": candidate["artifact_path"], "temporal": candidate["temporal"], "record": projected})


def _sections(corpus, modern_discovery, modern_genuine, legacy_chain, modern_chain, chain,
              *, snapshots_sessions, aggregate: _Aggregator) -> dict[str, Any]:
    false_negatives, failed_setups = aggregate.false_negatives, aggregate.failed_setups
    required = {ticker: aggregate.required[ticker] or [{"ticker": ticker, "status": "NO_PROSPECTIVE_CASE"}] for ticker in fb.REQUIRED_TICKERS}
    policy_candidates = [{
        "disposition": "MORE_PROSPECTIVE_EVIDENCE_REQUIRED", "current_rule": "Outcome feedback never mutates current daily posture policy.",
        "observed_prospective_counterexamples": len(false_negatives) + len(failed_setups), "sample_size": aggregate.t5_mature,
        "why_current_rule_may_be_too_restrictive_or_loose": "No mature T5 close-return sample exists in the temporally qualified corpus.",
        "possible_bounded_change": None, "expected_affected_cohort": None, "risk_of_change": "LOOK_AHEAD_OR_THIN_SAMPLE_OVERFIT",
        "evidence_strength": "INSUFFICIENT", "policy_mutated": False,
    }]
    corpus_health = retention.build_corpus_health(snapshot_inventory=modern_discovery, feedback_artifact={"feedback_records": aggregate.health_rows})
    horizon_coverage = {name: dict(sorted(counter.items())) for name, counter in aggregate.horizon_coverage.items()}
    # The inventory rows reference handles only for genuine entries; make them plain data.
    return {
        "schema_version": "1.0.0", "contract_version": fb.CONTRACT_VERSION, "outcome_policy_constants": fb.OUTCOME_POLICY_CONSTANTS,
        "prospective_corpus": {"candidate_artifact_count": len(corpus["inventory"]), "genuine_artifact_count": len(corpus["genuine_artifacts"]),
                               "immutable_snapshot_count": len(modern_discovery["inventory"]), "genuine_immutable_snapshot_count": len(modern_genuine),
                               "genuine_decision_count": aggregate.count, "unique_sessions": sorted(set(legacy_chain) | set(modern_chain)),
                               "unique_tickers": len(aggregate.tickers), "classification_counts": corpus["classification_counts"],
                               "snapshot_classification_counts": modern_discovery["classification_counts"]},
        "temporal_qualification": {"artifact_inventory": corpus["inventory"], "immutable_snapshot_inventory": modern_discovery["inventory"],
                                   "handoff_snapshot_inventory": modern_discovery["handoff_snapshot_inventory"], "qualified_session_chain": chain,
                                   "retained_snapshot_sessions": snapshots_sessions,
                                   "temporal_gate": "LEGACY_CANONICAL_HANDOFF_OR_IMMUTABLE_T0_SNAPSHOT_PLUS_RETAINED_DAILY_OPERATION"},
        "forward_outcome_coverage": {"horizons": horizon_coverage, "close_excursions": {"CLOSE_MFE_CLOSE_MAE_ONLY": True, "intraday_mfe_mae": "NOT_CLAIMED"}},
        "posture_outcome_summary": fb._summary(aggregate.by_posture, dimension="research_action_posture"),
        "coherence_outcome_summary": fb._summary(aggregate.by_coherence, dimension="evidence_axis_coherence"),
        "evidence_axis_outcome_summary": fb._summary(aggregate.by_axis, dimension="evidence_axis_state"),
        "false_negative_cases": false_negatives, "failed_setup_cases": failed_setups,
        "prospective_corpus_health": corpus_health, "policy_diagnostic_candidates": policy_candidates, "required_ticker_cases": required,
        "authority_boundary": {"downstream_observation_only": True, "no_retroactive_recommendation_reconstruction": True, "no_policy_mutation": True,
                               "no_probability_or_calibration": True, "no_raw_as_traded_or_pit_authority": True, "no_daily_decision_feedback_loop": True},
    }


def _assemble(final_tmp: Path, sections: Mapping[str, Any], rows: _Spool, triggers: _Spool, metrics) -> tuple[str, int, str, int]:
    """Write ``{"artifact_identity":…,<canonical members>}`` and hash the canonical members as they are written."""
    placeholder = ARTIFACT_IDENTITY_PREFIX + "0" * 64
    head = b'{"artifact_identity":"' + placeholder.encode() + b'",'
    streamed = {"feedback_records": rows, "trigger_invalidation_outcomes": triggers}
    keys = sorted(set(sections) | set(streamed))
    digest = hashlib.sha256()
    with open(final_tmp, "wb", buffering=1 << 20) as out:
        out.write(head)

        def emit(block: bytes) -> None:
            out.write(block)
            digest.update(block)

        digest.update(b"{")  # the file's opening brace is part of ``head``; the hash needs its own
        for position, key in enumerate(keys):
            if position:
                emit(b",")
            emit(json.dumps(key, ensure_ascii=False).encode("utf-8") + b":")
            if key in streamed:
                emit(b"[")
                _copy_hashing(streamed[key].path, [emit])
                emit(b"]")
            else:
                emit(_canon_bytes(sections[key]))
        emit(b"}")
        identity = ARTIFACT_IDENTITY_PREFIX + digest.hexdigest()
        out.seek(len(b'{"artifact_identity":"'))
        out.write(identity.encode())
        out.flush()
        os.fsync(out.fileno())
        size = out.seek(0, os.SEEK_END)
    # Re-read the bytes that reached disk: the identity member plus the hashed body must reproduce the digest.
    check = hashlib.sha256()
    check.update(b"{")
    with open(final_tmp, "rb") as written:
        written.seek(len(head))
        for block in iter(lambda: written.read(1 << 20), b""):
            check.update(block)
    if check.hexdigest() != digest.hexdigest():
        raise FeedbackStreamError("FEEDBACK_OUTPUT_READBACK_MISMATCH")
    raw_sha = bas.source_hash(final_tmp)
    _metric(metrics, "output_bytes", size)
    return identity, size, raw_sha, rows.count


class _ArrayStream(bas.ObjectStream):
    """ObjectStream that can also walk a JSON array element by element (bounded by one element)."""

    def elements(self):
        self.take("[")
        if self.peek() == "]":
            self.take("]")
            return
        while True:
            yield self.value()
            if self.peek() == "]":
                self.take("]")
                return
            self.take(",")


ARRAY_MEMBERS = frozenset({"feedback_records", "trigger_invalidation_outcomes"})


def stream_artifact_identity(path: Path) -> str:
    """Recompute ``artifact_identity`` of a feedback artifact of either layout without materialising it."""
    digest = hashlib.sha256()
    digest.update(b"{")
    first = True
    with open(path, encoding="utf-8") as source:
        parser = _ArrayStream(source, sorted_required=True)
        for key in parser.members():
            included = key != "artifact_identity"
            if included:
                if not first:
                    digest.update(b",")
                first = False
                digest.update(json.dumps(key, ensure_ascii=False).encode("utf-8") + b":")
            if key in ARRAY_MEMBERS:
                if included:
                    digest.update(b"[")
                for position, element in enumerate(parser.elements()):
                    if included:
                        if position:
                            digest.update(b",")
                        digest.update(_canon_bytes(element))
                if included:
                    digest.update(b"]")
            else:
                value = parser.value()
                if included:
                    digest.update(_canon_bytes(value))
        if parser.peek():
            raise ValueError("FEEDBACK_ARTIFACT_TRAILING_JSON")
    digest.update(b"}")
    return ARTIFACT_IDENTITY_PREFIX + digest.hexdigest()


def _publish(final_tmp: Path, output: Path, identity: str, size: int, raw_sha: str, record_count: int,
             input_digest: str, code: str, inputs_summary: Mapping[str, Any]) -> str:
    """Atomic COMPLETE publication. An existing artifact is accepted only if it provably carries the same content."""
    if output.exists():
        completion = read_completion(output)
        if completion is not None and completion.get("artifact_identity") == identity:
            return OUTCOME_ALREADY_RETAINED_EQUAL
        existing_sha = bas.source_hash(output)
        equal = existing_sha == raw_sha
        if not equal and _identity_from_header(output) == identity:
            # A same-identity artifact in another layout (the original builder's indent=2 file): prove it by content.
            try:
                equal = stream_artifact_identity(output) == identity
            except (OSError, ValueError):
                equal = False
        if not equal:
            raise ImmutableOutputConflict("IMMUTABLE_ARTIFACT_CONFLICT:" + str(output))
        _write_completion(output, identity, output.stat().st_size, existing_sha, record_count, input_digest, code, inputs_summary)
        return OUTCOME_ALREADY_RETAINED_EQUAL
    os.replace(final_tmp, output)
    _write_completion(output, identity, size, raw_sha, record_count, input_digest, code, inputs_summary)
    return OUTCOME_BUILT


def _write_completion(output: Path, identity, size, raw_sha, record_count, input_digest, code, inputs_summary) -> None:
    manifest = {"contract_version": COMPLETION_CONTRACT_VERSION, "artifact_identity": identity, "artifact_path": output.name,
                "artifact_size": size, "artifact_raw_sha256": raw_sha, "record_count": record_count, "input_digest": input_digest,
                "code_digest": code, "inputs_summary": dict(inputs_summary), "format": "canonical_compact_json"}
    _atomic_write_json(completion_manifest_path(output), manifest, allow_nan=False)


def _adopt_existing(output, identity, size, raw_sha, record_count, input_digest, code, inputs_summary):
    _write_completion(output, identity, output.stat().st_size, bas.source_hash(output), record_count, input_digest, code, inputs_summary)
    return read_completion(output)


def _result(outcome: str, output: Path, manifest: Mapping[str, Any] | None, inputs_summary, relation, metrics, phases) -> dict[str, Any]:
    manifest = manifest or {}
    return {"contract_version": RESULT_CONTRACT_VERSION, "outcome": outcome, "artifact_identity": manifest.get("artifact_identity"),
            "path": str(output), "artifact_size": manifest.get("artifact_size"), "artifact_raw_sha256": manifest.get("artifact_raw_sha256"),
            "record_count": manifest.get("record_count"), "input_digest": inputs_summary["input_digest"],
            "inputs_summary": dict(inputs_summary), "relation": relation, "metrics": dict(metrics),
            "phases_seconds": {k: round(v, 3) for k, v in phases.items()}}
