"""Read-only verified projections. No decision classifier or publication authority."""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import time
from pathlib import Path

from stocklookup_core.evidence.artifact_stream import ObjectStream
from stocklookup_core.evidence.bounded_json import canonical_bytes
from stocklookup_core.decision import integrated_investment_decision_product as iid

CONTRACT = "action_center_selected_research_preview/v1"
MAX_SELECTED = 20
MEMBER_LIMIT = 4 * 1024 * 1024  # decoded characters; UTF-8 bytes can be up to four times larger
METADATA_LIMIT = 4 * 1024 * 1024
MAX_SOURCE_BYTES = 4 * 1024**3
MAX_SELECTED_BYTES = 16 * 1024 * 1024
MIN_AVAILABLE_BYTES = 1024**3
DEADLINE_SECONDS = 600


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("ACCEPTANCE_NESTED_DUPLICATE_KEY:" + key)
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("ACCEPTANCE_NONFINITE_NUMBER:" + value)


def finite_float(value):
    result = float(value)
    if not math.isfinite(result):
        reject_constant(value)
    return result


class _PreviewObjectStream(ObjectStream):
    """Preview-only restrictions over the frozen E4 member traversal/refill strategy."""

    def __init__(self, source, *, limit, deadline):
        super().__init__(source, limit=limit)
        self.deadline = deadline
        self.decoder = json.JSONDecoder(object_pairs_hook=strict_object,
                                        parse_constant=reject_constant, parse_float=finite_float)

    def fill(self, size=64 * 1024):
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise ValueError("ACCEPTANCE_DEADLINE_EXCEEDED")
        remaining = self.limit - (len(self.buffer) - self.position)
        if remaining <= 0:
            raise ValueError("ACCEPTANCE_JSON_MEMBER_LIMIT")
        super().fill(min(size, remaining))

    def peek(self):
        # JSON permits only these four whitespace characters, unlike str.isspace().
        while True:
            while self.position < len(self.buffer) and self.buffer[self.position] in " \t\r\n":
                self.position += 1
            if self.position < len(self.buffer):
                return self.buffer[self.position]
            if self.eof:
                return ""
            self.fill()


def _stream_artifact(path, *, excluded, on_record, member_limit=MEMBER_LIMIT,
                     metadata_limit=METADATA_LIMIT, deadline=None):
    """Preview-scoped native canonical hash; E4's public verifier has no parser injection.

    Reuse its sorted-unique traversal and adaptive member decoding without changing
    the frozen API or any other consumer. Hash all records, including unselected rows.
    """
    digest = hashlib.sha256(b"{")
    metadata, first, count, metadata_size = {}, True, 0, 0

    def encode(value):
        digest.update(canonical_bytes(value))

    with path.open(encoding="utf-8") as source:
        parser = _PreviewObjectStream(source, limit=member_limit, deadline=deadline)
        for key in parser.members():
            included = key not in excluded
            if included:
                if not first:
                    digest.update(b",")
                first = False
                encode(key)
                digest.update(b":")
            if key == "records":
                if not included:
                    raise ValueError("ACCEPTANCE_RECORDS_EXCLUDED")
                digest.update(b"{")
                record_first = True
                for ticker in parser.members():
                    row = parser.value()
                    if not record_first:
                        digest.update(b",")
                    record_first = False
                    encode(ticker)
                    digest.update(b":")
                    encode(row)
                    on_record(ticker, row)
                    count += 1
                digest.update(b"}")
            else:
                value = parser.value()
                metadata_size += len(canonical_bytes(value))
                if metadata_size > metadata_limit:
                    raise ValueError("ACCEPTANCE_METADATA_LIMIT")
                metadata[key] = value
                if included:
                    encode(value)
        if parser.peek():
            raise ValueError("ACCEPTANCE_TRAILING_JSON")
    digest.update(b"}")
    return metadata, digest.hexdigest(), count


def resource_gate(*, available_bytes=None):
    if available_bytes is None:
        import psutil
        available_bytes = psutil.virtual_memory().available
    if available_bytes < MIN_AVAILABLE_BYTES:
        raise ValueError("PREVIEW_RESOURCE_BUDGET_REFUSED")
    return {"available_physical_bytes": available_bytes,
            "minimum_available_physical_bytes": MIN_AVAILABLE_BYTES,
            "member_character_limit": MEMBER_LIMIT, "max_selected_tickers": MAX_SELECTED,
            "max_source_bytes": MAX_SOURCE_BYTES, "deadline_seconds": DEADLINE_SECONDS}


def small_json(path, *, limit=METADATA_LIMIT):
    path = Path(path)
    if path.stat().st_size > limit:
        raise ValueError("PREVIEW_METADATA_FILE_LIMIT")
    with path.open(encoding="utf-8") as source:
        text = source.read(limit + 1)
    if len(text) > limit:
        raise ValueError("PREVIEW_METADATA_FILE_LIMIT")
    return json.loads(text, object_pairs_hook=strict_object,
                      parse_constant=reject_constant, parse_float=finite_float)


def select_tickers(tickers):
    if isinstance(tickers, str):
        raise ValueError("PREVIEW_EXPLICIT_TICKER_SEQUENCE_REQUIRED")
    values = list(itertools.islice(tickers, MAX_SELECTED + 1))
    if not values or len(values) > MAX_SELECTED or any(
        not isinstance(t, str) or not t or len(t) > 32 or not t.isascii()
        or not all(c.isalnum() or c == '_' for c in t) for t in values
    ) or len(set(values)) != len(values):
        raise ValueError("PREVIEW_SELECTION_LIMIT_OR_INVALID_TICKER")
    return tuple(sorted(values))


def validate_price_dimensions(previous, current):
    """Reject conflicting declared dimensions; never infer a missing currency or scale."""
    for dimension in ("price_unit", "currency", "scale"):
        values = []
        for record in (previous, current):
            for role in ("trigger", "invalidation"):
                value = (((record or {}).get(role) or {}).get("price_basis") or {}).get(dimension)
                if value is not None and value not in values:
                    values.append(value)
        if len(values) > 1:
            raise ValueError("PREVIEW_PRICE_DIMENSION_CONFLICT:" + dimension)


def verified_projection(path, *, session, expected_identity, tickers, deadline,
                        contract=iid.CONTRACT_VERSION, identity_prefix=None,
                        excluded=None, validate_record=None):
    """Hash every member, validate every record, expose selected rows only AFTER EOF proof.

    Native IID identity excludes requested_at; other callers must supply their exact exclusions.
    The original artifact identity is lineage, never the identity of this selected mapping.
    """
    path = Path(path)
    before = path.stat()
    if not 0 < before.st_size <= MAX_SOURCE_BYTES:
        raise ValueError("PREVIEW_SOURCE_SIZE_REFUSED")
    selected = {}
    wanted = set(tickers)
    selected_bytes = 0
    epochs = set()

    def consume(ticker, row):
        nonlocal selected_bytes
        if time.monotonic() >= deadline:
            raise ValueError("ACCEPTANCE_DEADLINE_EXCEEDED")
        if not isinstance(row, dict):
            raise ValueError("PREVIEW_RECORD_INVALID:" + ticker)
        if contract == iid.CONTRACT_VERSION:
            if row.get("ticker") != ticker or row.get("as_of_session") != session:
                raise ValueError("PREVIEW_RECORD_SESSION_OR_TICKER_MISMATCH:" + ticker)
            if row.get("decision_identity") != iid.decision_identity(row):
                raise ValueError("PREVIEW_DECISION_IDENTITY_MISMATCH:" + ticker)
            iid.validate_posture_policy(row)
            epochs.add(iid.research_policy_epoch(row))
        if validate_record is not None:
            validate_record(ticker, row)
        if ticker in wanted:
            selected_bytes += len(canonical_bytes(row))
            if selected_bytes > MAX_SELECTED_BYTES:
                raise ValueError("PREVIEW_SELECTED_PAYLOAD_LIMIT")
            selected[ticker] = row

    metadata, digest, count = _stream_artifact(
        path, excluded=iid._IDENTITY_EXCLUDED if excluded is None else excluded,
        on_record=consume, member_limit=MEMBER_LIMIT,
        metadata_limit=METADATA_LIMIT, deadline=deadline,
    )
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (
        after.st_size, after.st_mtime_ns, after.st_ino
    ):
        raise ValueError("PREVIEW_SOURCE_CHANGED_DURING_VERIFICATION")
    identity = f"{identity_prefix or contract}:{digest}"
    if (metadata.get("contract_version") != contract or metadata.get("session") != session
            or metadata.get("artifact_sha256") != digest
            or metadata.get("artifact_identity") != identity or expected_identity != identity):
        raise ValueError("PREVIEW_SOURCE_CONTRACT_SESSION_OR_IDENTITY_MISMATCH")
    if contract == iid.CONTRACT_VERSION:
        if metadata.get("schema_version") != "integrated_investment_decision_product/1.0.0":
            raise ValueError("PREVIEW_SOURCE_SCHEMA_MISMATCH")
        root_epoch = metadata.get("research_action_policy_version", "v1")
        if epochs != {root_epoch}:
            raise ValueError("PREVIEW_ROOT_RECORD_POLICY_MISMATCH")
        coverage = metadata.get("coverage") or {}
        if any(coverage[k] != count for k in ("universe_denominator", "integrated_context_available") if k in coverage):
            raise ValueError("PREVIEW_SOURCE_DENOMINATOR_MISMATCH")
    # Return a projection envelope, never an incomplete source artifact passed to a full builder.
    return {"source_metadata": metadata, "selected_records": selected,
            "source_identity": identity, "source_record_count": count,
            "source_bytes": before.st_size, "verification": "FULL_NATIVE_CONTENT_VERIFIED"}


def identity(body):
    payload = {k: v for k, v in body.items() if k not in {"artifact_identity", "artifact_sha256"}}
    digest = hashlib.sha256(canonical_bytes(payload)).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"{CONTRACT}:{digest}"}
