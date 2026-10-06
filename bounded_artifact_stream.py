"""Bounded sorted-JSON parsing and canonical hash verification."""
import hashlib
import json
import re
import os
import prospective_decision_retention as retention
from field_temporal_contract import _sanitize_for_json

class ObjectStream:
    """Bounded stdlib JSON object reader; never materialize the records container."""
    def __init__(self, source, *, limit=16 * 1024 * 1024, sorted_required=True):
        # ``sorted_required=False`` is for projection-only readers that never hash canonical bytes;
        # duplicate keys are still rejected (fail closed) via the seen-set below.
        self.source, self.limit, self.sorted_required = source, limit, sorted_required
        self.buffer, self.position, self.eof = "", 0, False
        self.decoder = json.JSONDecoder()
        self.hint = 0  # characters of the last large member; sizes the next refill so a record is decoded ~once

    def fill(self, size=64 * 1024):
        self.buffer = self.buffer[self.position:]
        self.position = 0
        chunk = self.source.read(size)
        self.eof = not chunk
        self.buffer += chunk
        if len(self.buffer) > self.limit:
            raise ValueError("ACCEPTANCE_JSON_MEMBER_LIMIT")

    def peek(self):
        while True:
            while self.position < len(self.buffer) and self.buffer[self.position].isspace():
                self.position += 1
            if self.position < len(self.buffer):
                return self.buffer[self.position]
            if self.eof:
                return ""
            self.fill()

    def take(self, expected):
        if self.peek() != expected:
            raise ValueError("ACCEPTANCE_JSON_SYNTAX")
        self.position += 1

    def value(self):
        self.peek()
        # Refill is sized from the previous large member and doubles on failure, so a record is
        # re-scanned O(1) times instead of once per 64 KiB chunk.
        want = min(max(64 * 1024, int(self.hint * 1.25)), self.limit // 2)  # prefill never pushes a legal member over the limit
        if len(self.buffer) - self.position < want and not self.eof:
            self.fill(want - (len(self.buffer) - self.position))
        while True:
            try:
                value, end = self.decoder.raw_decode(self.buffer, self.position)
                # A numeric token at a chunk boundary might be only a prefix.
                numeric_prefix = isinstance(value, (int, float)) and end < len(self.buffer) and self.buffer[end] not in " \t\r\n,]}"
                if (end == len(self.buffer) or numeric_prefix) and not self.eof:
                    self.fill(want)
                    want = min(want * 2, self.limit)
                    continue
                if end - self.position > 4096:
                    self.hint = end - self.position
                self.position = end
                return value
            except json.JSONDecodeError:
                if self.eof:
                    raise
                self.fill(want)
                want = min(want * 2, self.limit)

    def members(self):
        self.take("{")
        if self.peek() == "}":
            self.take("}")
            return
        previous = None
        seen = set() if not self.sorted_required else None
        while True:
            key = self.value()
            if self.sorted_required:
                if not isinstance(key, str) or previous is not None and key <= previous:
                    raise ValueError("ACCEPTANCE_OBJECT_NOT_SORTED_UNIQUE")
            else:
                if not isinstance(key, str) or key in seen:
                    raise ValueError("ACCEPTANCE_OBJECT_DUPLICATE_OR_NON_STRING_KEY")
                seen.add(key)
            previous = key
            self.take(":")
            yield key
            next_character = self.peek()
            if next_character == "}":
                self.take("}")
                return
            self.take(",")


def canonical_bytes(value):
    """One-shot canonical UTF-8 bytes; byte-identical to the concatenated retention._json_bytes chunks."""
    return json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(value).encode("utf-8")


def record_mapping_digest(value):
    """Hash a string-keyed artifact exactly, encoding one records member at a time.

    Equivalent to sha256(canonical_bytes(value)); avoids the whole canonical
    Unicode string and UTF-8 bytes coexisting with the resident object graph.
    Non-record metadata retains the same strict stdlib JSON semantics.
    """
    # Non-string JSON keys are outside the artifact schema, but the helper must
    # preserve stdlib behavior (including mixed-key errors) rather than hash an
    # invalid unquoted key. Valid artifact universes stay on the bounded path.
    records = value.get("records")
    if (any(not isinstance(key, str) for key in value)
            or isinstance(records, dict) and any(not isinstance(key, str) for key in records)):
        return hashlib.sha256(canonical_bytes(value)).hexdigest()
    digest = hashlib.sha256()
    digest.update(b"{")
    for index, key in enumerate(sorted(value)):
        if index:
            digest.update(b",")
        digest.update(canonical_bytes(key))
        digest.update(b":")
        member = value[key]
        if key == "records" and isinstance(member, dict):
            digest.update(b"{")
            for record_index, ticker in enumerate(sorted(member)):
                if record_index:
                    digest.update(b",")
                digest.update(canonical_bytes(ticker))
                digest.update(b":")
                digest.update(canonical_bytes(member[ticker]))
            digest.update(b"}")
        elif key == "records" and isinstance(member, list):
            digest.update(b"[")
            for record_index, record in enumerate(member):
                if record_index:
                    digest.update(b",")
                digest.update(canonical_bytes(record))
            digest.update(b"]")
        else:
            digest.update(canonical_bytes(member))
    digest.update(b"}")
    return digest.hexdigest()


def pretty_record_chunks(value):
    """Native-newline stdlib indent=2 bytes, with one record-sized text at a time.

    Caller selects the string-keyed root/records schema. Other metadata remains
    bounded by its field size. No complete records container is encoded.
    """
    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True, indent=2)
    keys = sorted(value)
    def encoded(text): return text.replace('\n', os.linesep).encode('utf-8')
    if not keys:
        yield encoded('{}\n')
        return
    yield encoded('{\n')
    for index,key in enumerate(keys):
        yield encoded('  '+encoder.encode(key)+': ')
        member = value[key]
        if key == 'records' and isinstance(member,(dict,list)):
            mapping = isinstance(member,dict)
            if not member:
                yield b'{}' if mapping else b'[]'
            else:
                yield encoded('{\n' if mapping else '[\n')
                members = sorted(member) if mapping else range(len(member))
                for position,name in enumerate(members):
                    prefix = '    '+encoder.encode(name)+': ' if mapping else '    '
                    record = member[name]
                    yield encoded(prefix+encoder.encode(record).replace('\n','\n    '))
                    yield encoded(',\n' if position+1<len(member) else '\n')
                yield b'  }' if mapping else b'  ]'
        else:
            yield encoded(encoder.encode(member).replace('\n','\n  '))
        yield encoded(',\n' if index+1<len(keys) else '\n')
    yield encoded('}\n')


def source_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def header(path):
    """Bounded sideband locator; full stream later verifies these exact values."""
    with path.open("rb") as source:
        beginning = source.read(64 * 1024)
        source.seek(max(0, path.stat().st_size - 128 * 1024))
        ending = source.read()
    text = (beginning + b"\n" + ending).decode("utf-8", errors="replace")
    found = {}
    for key in ("snapshot_identity", "snapshot_sha256", "resolved_completed_session", "requested_at", "artifact_identity", "artifact_sha256", "session"):
        matches = re.findall(r'^  "' + key + r'": (.*?)[,]?\r?$', text, flags=re.MULTILINE)
        if matches:
            found[key] = json.loads(matches[-1].rstrip(","))
    return found


def stream_artifact(path, *, excluded, on_record, sanitize=False):
    digest = hashlib.sha256()
    digest.update(b"{")
    metadata, first, count = {}, True, 0
    def encode(value):
        if sanitize:
            for chunk in retention._json_bytes(_sanitize_for_json(value)):
                digest.update(chunk)
        else:
            # Same canonical bytes as retention._json_bytes (verified by test), without the pure-Python iterencode path.
            digest.update(canonical_bytes(value))
    with path.open(encoding="utf-8") as source:
        parser = ObjectStream(source)
        for key in parser.members():
            included = key not in excluded
            if included:
                if not first: digest.update(b",")
                first = False
                encode(key);digest.update(b":")
            if key == "records":
                if not included: raise ValueError("ACCEPTANCE_RECORDS_EXCLUDED")
                digest.update(b"{")
                record_first = True
                for ticker in parser.members():
                    row = parser.value()
                    if not record_first: digest.update(b",")
                    record_first = False
                    encode(ticker);digest.update(b":");encode(row)
                    on_record(ticker, row)
                    count += 1
                digest.update(b"}")
            else:
                value = parser.value()
                metadata[key] = value
                if included: encode(value)
        if parser.peek(): raise ValueError("ACCEPTANCE_TRAILING_JSON")
    digest.update(b"}")
    return metadata, digest.hexdigest(), count


