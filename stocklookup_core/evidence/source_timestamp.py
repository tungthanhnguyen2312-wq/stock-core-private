"""Explicit, timezone-aware source-generation timestamps for derived snapshots."""
from __future__ import annotations

from datetime import datetime, timezone


def resolve_source_datetime(value: str | datetime | None = None) -> datetime:
    if value is None:
        parsed = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("source generated-at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("source generated-at must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def source_timestamp(value: str | datetime | None = None) -> str:
    return resolve_source_datetime(value).isoformat(timespec="seconds").replace("+00:00", "Z")
