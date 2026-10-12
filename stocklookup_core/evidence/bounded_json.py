"""Exact compact/pretty UTF-8 encoding, bounded by token or individual record.

Compact rejects nonfinite floats; pretty retains stdlib permissive behaviour and
native newline translation. A single large JSON token may exceed 64 KiB.
"""
import hashlib
import json
import os
from typing import Any


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


def json_bytes(value: Any, *, pretty: bool = False):
    """Bounded encoding batches; canonical bytes match the standing dumps contract.

    Pretty output preserves the old text writer's native newline translation.
    Canonical identity bytes always use the original compact UTF-8 representation.
    """
    records = value.get('records') if isinstance(value,dict) else None
    if (pretty and isinstance(records,(dict,list)) and all(isinstance(k,str) for k in value)
            and (not isinstance(records,dict) or all(isinstance(k,str) for k in records))):
        yield from pretty_record_chunks(value)
        return
    encoder = (json.JSONEncoder(ensure_ascii=False, sort_keys=True, indent=2) if pretty else
               json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))
    buffer = bytearray()
    for chunk in encoder.iterencode(value):
        data = (chunk.replace("\n", os.linesep) if pretty else chunk).encode("utf-8")
        if len(buffer) + len(data) > 64 * 1024:
            if buffer:
                yield bytes(buffer)
                buffer.clear()
            if len(data) > 64 * 1024:
                yield data
                continue
        buffer.extend(data)
    if pretty:
        buffer.extend(os.linesep.encode("utf-8"))
    if buffer:
        yield bytes(buffer)
