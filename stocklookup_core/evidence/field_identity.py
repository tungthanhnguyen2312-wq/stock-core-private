"""Exact historical field-envelope JSON and SHA identity, independent of freshness.

NaN becomes null, tuples become lists, other unsupported values use default=str,
and infinities fail. This differs from the strict E4 bounded artifact encoder;
neither schema's canonical byte contract is substituted for the other.
"""
from __future__ import annotations
import hashlib
import json
import math
from typing import Any


def _sanitize_for_json(val: Any) -> Any:
    if isinstance(val, float) and math.isnan(val):
        return None
    if isinstance(val, dict):
        return {k: _sanitize_for_json(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_sanitize_for_json(v) for v in val]
    return val


def canonical_json(value: Any) -> str:
    """Deterministic JSON serialization with sorted keys and no floating point NaN."""
    sanitized = _sanitize_for_json(value)
    return json.dumps(sanitized, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False, default=str)


def stable_id(value: Any) -> str:
    """Deterministic SHA-256 digest of canonical JSON."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
