"""Deterministic, evidence-addressed trading-session calendars.

This contract deliberately separates the exchange-session calendar from any
dataset's observed partitions.  A canonical-Trades gap is coverage evidence;
it cannot make an otherwise governed trading session invalid.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


CONTRACT_VERSION = "governed_trading_session_calendar/v1"
CALENDAR_SOURCE_KIND = "EXPLICIT_GOVERNED_SESSION_EVIDENCE"
TARGET_SESSION_VALID = "TARGET_SESSION_VALID"
TARGET_SESSION_INVALID = "TARGET_SESSION_NOT_IN_GOVERNED_CALENDAR"


class GovernedTradingSessionCalendarError(ValueError):
    """A supplied calendar cannot establish an analytical session contract."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(payload: Mapping[str, Any]) -> dict[str, str]:
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return {"calendar_sha256": digest, "calendar_identity": f"governed_trading_session_calendar:{digest}"}


def _validate_sessions(values: Iterable[Any]) -> tuple[str, ...]:
    sessions = tuple(str(value) for value in values)
    if not sessions or any(len(value) != 10 or value[4] != "-" or value[7] != "-" for value in sessions):
        raise GovernedTradingSessionCalendarError("GOVERNED_SESSION_DATE_INVALID")
    if tuple(sorted(sessions)) != sessions or len(set(sessions)) != len(sessions):
        raise GovernedTradingSessionCalendarError("GOVERNED_SESSION_ORDER_OR_DUPLICATE_INVALID")
    return sessions


@dataclass(frozen=True)
class GovernedTradingSessionCalendar:
    """An immutable exact-session calendar backed by retained governance evidence."""

    sessions: tuple[str, ...]
    source: Mapping[str, Any]
    identity: str
    sha256: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "GovernedTradingSessionCalendar":
        if not isinstance(payload, Mapping) or payload.get("contract_version") != CONTRACT_VERSION:
            raise GovernedTradingSessionCalendarError("UNSUPPORTED_GOVERNED_SESSION_CALENDAR_CONTRACT")
        source = payload.get("source")
        if not isinstance(source, Mapping) or source.get("kind") != CALENDAR_SOURCE_KIND:
            raise GovernedTradingSessionCalendarError("GOVERNED_SESSION_SOURCE_UNPROVEN")
        sessions = _validate_sessions(payload.get("sessions") or [])
        identity = _identity({"contract_version": CONTRACT_VERSION, "source": dict(source), "sessions": list(sessions)})
        declared = payload.get("calendar_identity")
        if declared is not None and declared != identity["calendar_identity"]:
            raise GovernedTradingSessionCalendarError("GOVERNED_SESSION_CALENDAR_IDENTITY_MISMATCH")
        return cls(sessions=sessions, source=dict(source), identity=identity["calendar_identity"], sha256=identity["calendar_sha256"])

    def is_valid_target(self, target_session: str) -> bool:
        return str(target_session) in self.sessions

    def resolve_window(self, target_session: str, size: int) -> dict[str, Any]:
        if size <= 0:
            raise GovernedTradingSessionCalendarError("GOVERNED_SESSION_WINDOW_SIZE_INVALID")
        target = str(target_session)
        if target not in self.sessions:
            return {
                "state": TARGET_SESSION_INVALID,
                "target_session": target,
                "expected_sessions": size,
                "sessions": [],
                "calendar_identity": self.identity,
            }
        eligible = [session for session in self.sessions if session <= target]
        return {
            "state": "RESOLVED" if len(eligible) >= size else "INSUFFICIENT_CALENDAR_HISTORY",
            "target_session": target,
            "target_session_state": TARGET_SESSION_VALID,
            "expected_sessions": size,
            "sessions": eligible[-size:],
            "calendar_identity": self.identity,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": CONTRACT_VERSION,
            "source": dict(self.source),
            "sessions": list(self.sessions),
            "calendar_identity": self.identity,
            "calendar_sha256": self.sha256,
        }


def load_governed_trading_session_calendar(path: Path | str) -> GovernedTradingSessionCalendar:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GovernedTradingSessionCalendarError(f"GOVERNED_SESSION_CALENDAR_UNREADABLE:{source}") from exc
    return GovernedTradingSessionCalendar.from_mapping(payload)


def calendar_from_sessions(sessions: Sequence[str], *, source: Mapping[str, Any]) -> GovernedTradingSessionCalendar:
    """Test/integration helper; production callers should load retained evidence."""
    return GovernedTradingSessionCalendar.from_mapping({
        "contract_version": CONTRACT_VERSION,
        "source": dict(source),
        "sessions": list(sessions),
    })
