"""Bounded sorted-JSON parsing and canonical hash verification."""
import hashlib
import json
import re
import prospective_decision_retention as retention
from field_temporal_contract import _sanitize_for_json

class ObjectStream:
    """Bounded stdlib JSON object reader; never materialize the records container."""
    def __init__(self, source, *, limit=16 * 1024 * 1024):
        self.source, self.limit = source, limit
        self.buffer, self.position, self.eof = "", 0, False
        self.decoder = json.JSONDecoder()

    def fill(self):
        self.buffer = self.buffer[self.position:]
        self.position = 0
        chunk = self.source.read(64 * 1024)
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
        while True:
            try:
                value, end = self.decoder.raw_decode(self.buffer, self.position)
                # A numeric token at a chunk boundary might be only a prefix.
                numeric_prefix = isinstance(value, (int, float)) and end < len(self.buffer) and self.buffer[end] not in " \t\r\n,]}"
                if (end == len(self.buffer) or numeric_prefix) and not self.eof:
                    self.fill()
                    continue
                self.position = end
                return value
            except json.JSONDecodeError:
                if self.eof:
                    raise
                self.fill()

    def members(self):
        self.take("{")
        if self.peek() == "}":
            self.take("}")
            return
        previous = None
        while True:
            key = self.value()
            if not isinstance(key, str) or previous is not None and key <= previous:
                raise ValueError("ACCEPTANCE_OBJECT_NOT_SORTED_UNIQUE")
            previous = key
            self.take(":")
            yield key
            next_character = self.peek()
            if next_character == "}":
                self.take("}")
                return
            self.take(",")


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
        for chunk in retention._json_bytes(_sanitize_for_json(value) if sanitize else value):
            digest.update(chunk)
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


