"""Deterministic Vietnam operational-time helper for generated timestamps.

Bare ``datetime.now().astimezone()`` silently adopts whichever timezone the executing host
happens to be in (a dev laptop, UTC CI, ...), so the same instant serializes differently
depending on where the code runs. This module always resolves the project's canonical
operational zone explicitly, so a generated timestamp is deterministic regardless of host.

Scope: operational/generated timestamps only (``generated_at``, ``measured_at``, and similar
fields). Does not apply to source-provided timestamps (see ``source_timestamp.py``),
``data_as_of``, market-session derivation, or any report/financial-period value.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def vn_now() -> datetime:
    """Current instant as a timezone-aware Asia/Ho_Chi_Minh datetime, independent of host OS timezone."""
    return datetime.now(VN_TZ)


def vn_now_iso() -> str:
    """``vn_now()`` serialized ISO-8601 with the explicit Vietnam offset, seconds precision."""
    return vn_now().isoformat(timespec="seconds")
