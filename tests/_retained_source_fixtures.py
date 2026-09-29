"""Synthetic historical-source outcomes; no provider package or worker import."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FetchOutcome:
    status: str
    data: Any = None
    lineage: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    transient_failure: bool = False
    request_attempts: int = 0
    retry_count: int = 0
    timeout_count: int = 0
    http_429_count: int = 0
    http_5xx_count: int = 0
    retry_after_seconds: float = 0.0


def healthy_sentinel_evidence(session: str, *, dnse_exact: int = 2) -> dict:
    """Synthetic retained evidence for pure quality-license contract tests."""
    return {
        "target_session": session,
        "dnse_exact_session_count": dnse_exact,
        "dnse_quality_sentinel": {
            "cohort_tickers": ["AAA"],
            "health": {"state": "DNSE_EXACT_AND_CORROBORATED", "dnse_assessed_count": 1,
                       "corroborated_count": 1, "conflict_count": 0, "uncorroborated_count": 0},
        },
        "degraded_provider_recovery": {"mode": "NOT_TRIGGERED"},
        "records": {},
    }
