"""Retained corporate-event knowledge proof at an explicit aware cutoff.

No acquisition, directory discovery, freshness policy or authority promotion.
Observation and optional publication times are independently bounded as before.
"""
from datetime import datetime


def context_known_by(context: dict, cutoff: datetime) -> bool:
    """All retained event observations must exist by an explicit aware cutoff.

    Acquisition start and the directory date are not knowledge-time proof.
    Missing observation time fails closed; absent publication time is not inferred.
    """
    if cutoff.tzinfo is None:
        raise ValueError("KNOWLEDGE_TIME_MUST_BE_TIMEZONE_AWARE")
    events = context.get("all_current_universe_event_records")
    if not isinstance(events, list):
        return False
    excluded = context.get("excluded_noncurrent_or_official_only_event_records", [])
    if not isinstance(excluded, list):
        return False
    events = events + excluded
    for event in events:
        if not isinstance(event, dict):
            return False
        observed = event.get("official_observed_at")
        if not observed:
            return False
        for value in (observed, event.get("published_at")):
            if value is None:
                continue
            try:
                stamp = datetime.fromisoformat(value)
            except (TypeError, ValueError):
                return False
            if stamp.tzinfo is None or stamp > cutoff:
                return False
    return True
