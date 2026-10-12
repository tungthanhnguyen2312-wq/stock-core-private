"""Provider-neutral shareholder source chain and provenance utilities.

This module is deliberately stdlib-only so source adapters and reconciliation
can be tested with offline fixtures.  The live vnstock dependency remains in
``shareholders_sync.py``.
"""

from __future__ import annotations

import csv
import hashlib
import json
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


DONE = "done"
SOURCE_EMPTY = "source_empty"
UNSUPPORTED = "unsupported"
PARSE_FAILED = "parse_failed"
NETWORK_FAILED = "network_failed"
STALE = "stale"
MANUAL_OVERRIDE = "manual_override"
NOT_QUERIED = "not_queried"

TERMINAL_FAILURE_STATUSES = {SOURCE_EMPTY, UNSUPPORTED, PARSE_FAILED, NETWORK_FAILED}
MANUAL_COLUMNS = (
    "ticker",
    "holder_name",
    "shares",
    "ownership_pct",
    "as_of_date",
    "source_name",
    "source_reference",
    "verified_at",
    "note",
)


class UnsupportedSourceError(RuntimeError):
    """The provider does not implement the shareholder endpoint."""


class NetworkSourceError(RuntimeError):
    """The provider could not be reached after its retry policy."""


class ParseShareholderError(ValueError):
    """A non-empty payload could not be normalized safely."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_timestamp(value: datetime | None = None) -> str:
    current = value or utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat(timespec="seconds")


def normalize_holder_name(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(text.casefold().split())


def _number(value: Any) -> float | int | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace(",", "")
    if not text or text.casefold() in {"nan", "none", "null", "n/a"}:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _date_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    candidate = text[:10]
    try:
        return date.fromisoformat(candidate).isoformat()
    except ValueError:
        return None


def _payload_rows(payload: Any) -> list[Mapping[str, Any]]:
    if payload is None:
        return []
    if hasattr(payload, "to_dict"):
        try:
            rows = payload.to_dict(orient="records")
        except TypeError:
            rows = payload.to_dict()
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        return [payload]
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        return [row for row in payload if isinstance(row, Mapping)]
    raise ParseShareholderError(f"unsupported payload type: {type(payload).__name__}")


@dataclass
class ShareholderRecord:
    ticker: str
    holder_name: str
    shares: float | int | None
    ownership_pct: float | int | None
    as_of_date: str | None
    source_name: str
    source_reference: str | None = None
    verified_at: str | None = None
    fetched_at: str | None = None
    note: str | None = None
    record_origin: str = "api"
    reconciliation_status: str = "accepted"
    conflict_group: str | None = None
    provenance: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.ticker = self.ticker.strip().upper()
        self.holder_name = " ".join(self.holder_name.split())
        if not self.provenance:
            self.provenance = [
                {
                    "source_name": self.source_name,
                    "source_reference": self.source_reference,
                    "record_origin": self.record_origin,
                    "verified_at": self.verified_at,
                    "fetched_at": self.fetched_at,
                }
            ]

    @property
    def normalized_holder_name(self) -> str:
        return normalize_holder_name(self.holder_name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "holder_name": self.holder_name,
            "normalized_holder_name": self.normalized_holder_name,
            "shares": self.shares,
            "ownership_pct": self.ownership_pct,
            "as_of_date": self.as_of_date,
            "source_name": self.source_name,
            "source_reference": self.source_reference,
            "verified_at": self.verified_at,
            "fetched_at": self.fetched_at,
            "note": self.note,
            "record_origin": self.record_origin,
            "reconciliation_status": self.reconciliation_status,
            "conflict_group": self.conflict_group,
            "provenance": list(self.provenance),
        }


@dataclass
class SourceAttempt:
    source: str
    status: str
    error_reason: str | None
    record_count: int
    parsed_record_count: int
    request_timestamp: str
    latest_as_of_date: str | None

    def to_dict(self) -> dict[str, Any]:
        error = self.error_reason if self.status in {UNSUPPORTED, PARSE_FAILED, NETWORK_FAILED} else None
        return {
            "source": self.source,
            "status": self.status,
            "error": error,
            "reason": self.error_reason,
            "error_reason": self.error_reason,
            "record_count": self.record_count,
            "parsed_record_count": self.parsed_record_count,
            "request_timestamp": self.request_timestamp,
            "latest_as_of_date": self.latest_as_of_date,
        }


@dataclass
class SourceChainResult:
    ticker: str
    records: list[ShareholderRecord]
    attempts: list[SourceAttempt]
    final_status: str
    reason: str
    raw_record_count: int
    parsed_record_count: int


@dataclass
class ShareholderSourceAdapter:
    source_name: str
    fetcher: Callable[[str], Any]
    parser: Callable[[Any, str, str, str | None], list[ShareholderRecord]]
    source_reference: str | None = None

    def attempt(self, ticker: str, requested_at: datetime | None = None) -> tuple[list[ShareholderRecord], SourceAttempt]:
        timestamp = iso_timestamp(requested_at)
        try:
            payload = self.fetcher(ticker)
        except (UnsupportedSourceError, NotImplementedError) as exc:
            return [], SourceAttempt(self.source_name, UNSUPPORTED, str(exc), 0, 0, timestamp, None)
        except (NetworkSourceError, TimeoutError, ConnectionError) as exc:
            return [], SourceAttempt(self.source_name, NETWORK_FAILED, str(exc), 0, 0, timestamp, None)
        try:
            rows = _payload_rows(payload)
        except ParseShareholderError as exc:
            return [], SourceAttempt(self.source_name, PARSE_FAILED, str(exc), 0, 0, timestamp, None)
        if not rows:
            return [], SourceAttempt(self.source_name, SOURCE_EMPTY, "provider_returned_empty_payload", 0, 0, timestamp, None)
        try:
            records = self.parser(rows, ticker, timestamp, self.source_reference)
        except (KeyError, TypeError, ValueError, ParseShareholderError) as exc:
            return [], SourceAttempt(self.source_name, PARSE_FAILED, str(exc), len(rows), 0, timestamp, None)
        if not records:
            return [], SourceAttempt(
                self.source_name,
                PARSE_FAILED,
                "non_empty_payload_has_no_usable_holder_rows",
                len(rows),
                0,
                timestamp,
                None,
            )
        latest = max((record.as_of_date for record in records if record.as_of_date), default=None)
        return records, SourceAttempt(self.source_name, DONE, None, len(rows), len(records), timestamp, latest)


def parse_provider_rows(
    rows: Any,
    ticker: str,
    requested_at: str,
    source_reference: str | None,
    *,
    source_name: str,
) -> list[ShareholderRecord]:
    records: list[ShareholderRecord] = []
    if source_name == "VCI":
        name_field, shares_field, pct_field, pct_scale = "share_holder", "quantity", "share_own_percent", 100.0
    elif source_name == "KBS":
        name_field, shares_field, pct_field, pct_scale = "name", "shares_owned", "ownership_percentage", 1.0
    else:
        raise UnsupportedSourceError(f"no parser configured for {source_name}")
    for row in _payload_rows(rows):
        holder_name = " ".join(str(row.get(name_field) or "").split())
        if not holder_name:
            continue
        raw_pct = _number(row.get(pct_field))
        pct = None if raw_pct is None else float(raw_pct) * pct_scale
        as_of = next(
            (_date_string(row.get(key)) for key in ("as_of_date", "update_date", "updated_at", "date") if _date_string(row.get(key))),
            None,
        )
        records.append(
            ShareholderRecord(
                ticker=ticker,
                holder_name=holder_name,
                shares=_number(row.get(shares_field)),
                ownership_pct=pct,
                as_of_date=as_of,
                source_name=source_name,
                source_reference=source_reference,
                fetched_at=requested_at,
            )
        )
    return records


def provider_parser(source_name: str) -> Callable[[Any, str, str, str | None], list[ShareholderRecord]]:
    return lambda rows, ticker, requested_at, reference: parse_provider_rows(
        rows,
        ticker,
        requested_at,
        reference,
        source_name=source_name,
    )


def _failure_status(attempts: Sequence[SourceAttempt]) -> str:
    statuses = {attempt.status for attempt in attempts}
    for status in (NETWORK_FAILED, PARSE_FAILED, SOURCE_EMPTY, UNSUPPORTED):
        if status in statuses:
            return status
    return NOT_QUERIED


def run_source_chain(
    ticker: str,
    adapters: Sequence[ShareholderSourceAdapter],
    requested_at: datetime | None = None,
) -> SourceChainResult:
    attempts: list[SourceAttempt] = []
    records: list[ShareholderRecord] = []
    chain_requested_at = requested_at or utc_now()
    for adapter in adapters:
        parsed, attempt = adapter.attempt(ticker.strip().upper(), requested_at=chain_requested_at)
        attempts.append(attempt)
        if parsed:
            records.extend(parsed)
            break
    status = DONE if records else _failure_status(attempts)
    reason = "usable_records_from_configured_source" if records else {
        NETWORK_FAILED: "configured_source_chain_had_network_failure",
        PARSE_FAILED: "configured_source_payload_could_not_be_parsed",
        SOURCE_EMPTY: "configured_sources_returned_no_usable_records",
        UNSUPPORTED: "configured_sources_do_not_support_shareholders",
        NOT_QUERIED: "no_sources_were_attempted",
    }[status]
    return SourceChainResult(
        ticker=ticker.strip().upper(),
        records=records,
        attempts=attempts,
        final_status=status,
        reason=reason,
        raw_record_count=sum(attempt.record_count for attempt in attempts),
        parsed_record_count=sum(attempt.parsed_record_count for attempt in attempts),
    )


def load_manual_overrides(path: Path, ticker: str | None = None) -> list[ShareholderRecord]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing_columns = [column for column in MANUAL_COLUMNS if column not in (reader.fieldnames or [])]
        if missing_columns:
            raise ValueError("manual override missing columns: " + ", ".join(missing_columns))
        records: list[ShareholderRecord] = []
        for line_number, row in enumerate(reader, 2):
            row_ticker = (row.get("ticker") or "").strip().upper()
            if ticker and row_ticker != ticker.strip().upper():
                continue
            required = ("ticker", "holder_name", "as_of_date", "source_name", "source_reference", "verified_at")
            absent = [column for column in required if not (row.get(column) or "").strip()]
            if absent:
                raise ValueError(f"manual override line {line_number} missing provenance: {', '.join(absent)}")
            as_of = _date_string(row.get("as_of_date"))
            if as_of is None:
                raise ValueError(f"manual override line {line_number} has invalid as_of_date")
            records.append(
                ShareholderRecord(
                    ticker=row_ticker,
                    holder_name=(row.get("holder_name") or "").strip(),
                    shares=_number(row.get("shares")),
                    ownership_pct=_number(row.get("ownership_pct")),
                    as_of_date=as_of,
                    source_name=(row.get("source_name") or "").strip(),
                    source_reference=(row.get("source_reference") or "").strip(),
                    verified_at=(row.get("verified_at") or "").strip(),
                    note=(row.get("note") or "").strip() or None,
                    record_origin="manual",
                )
            )
    return records


def _same_values(left: ShareholderRecord, right: ShareholderRecord) -> bool:
    return left.shares == right.shares and left.ownership_pct == right.ownership_pct


def deduplicate_records(records: Iterable[ShareholderRecord]) -> list[ShareholderRecord]:
    grouped: dict[tuple[str, str, str | None], list[ShareholderRecord]] = {}
    for record in records:
        key = (record.ticker, record.normalized_holder_name, record.as_of_date)
        grouped.setdefault(key, []).append(record)
    output: list[ShareholderRecord] = []
    for key, candidates in grouped.items():
        accepted: list[ShareholderRecord] = []
        for candidate in candidates:
            duplicate = next((item for item in accepted if _same_values(item, candidate)), None)
            if duplicate:
                for provenance in candidate.provenance:
                    if provenance not in duplicate.provenance:
                        duplicate.provenance.append(provenance)
                if duplicate.source_name != candidate.source_name:
                    duplicate.reconciliation_status = "matched_across_sources"
                continue
            accepted.append(candidate)
        if len(accepted) > 1:
            raw_group = "|".join(str(part or "") for part in key)
            group_id = hashlib.sha256(raw_group.encode("utf-8")).hexdigest()[:16]
            for candidate in accepted:
                candidate.reconciliation_status = "conflict_preserved"
                candidate.conflict_group = group_id
        output.extend(accepted)
    return sorted(
        output,
        key=lambda item: (
            item.ticker,
            item.as_of_date or "",
            item.normalized_holder_name,
            item.record_origin,
            item.source_name,
        ),
    )


MAJOR_SHAREHOLDER_SNAPSHOT_SCHEMA_VERSION = 1


def _strict_date_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def _snapshot_scope(record: Mapping[str, Any]) -> tuple[Any, Any, Any, Any]:
    return (
        record.get("ticker"),
        record.get("source_name"),
        record.get("record_origin"),
        record.get("source_reference"),
    )


def build_major_shareholder_snapshot_manifest(summary: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return a complete forward-only API snapshot manifest, or ``None``.

    Historical records are retained separately in ``shareholder_records_v2``.  A
    manifest is intentionally stricter: absence of a holder can only be used in
    a delta when the source response represents one complete, dated API scope.
    """
    records = [record for record in summary.get("records", ()) if record.get("record_origin") == "api"]
    if not records:
        return None

    source_names = {record.get("source_name") for record in records}
    done_sources = {
        attempt.get("source")
        for attempt in summary.get("attempts", ())
        if attempt.get("status") == DONE
    }
    if len(source_names) != 1 or source_names.isdisjoint(done_sources):
        return None

    scopes = {_snapshot_scope(record) for record in records}
    if len(scopes) != 1:
        return None
    ticker, source_name, record_origin, source_reference = next(iter(scopes))
    if not ticker or not source_name or record_origin != "api":
        return None

    as_of_dates = {_strict_date_string(record.get("as_of_date")) for record in records}
    fetched_at_values = {record.get("fetched_at") for record in records}
    normalized_names = [record.get("normalized_holder_name") for record in records]
    if (
        None in as_of_dates
        or len(as_of_dates) != 1
        or None in fetched_at_values
        or len(fetched_at_values) != 1
        or any(not name for name in normalized_names)
        or len(set(normalized_names)) != len(normalized_names)
        or any(record.get("reconciliation_status") == "conflict_preserved" for record in records)
    ):
        return None

    as_of_date = next(iter(as_of_dates))
    identity = json.dumps(
        [ticker, as_of_date, source_name, record_origin, source_reference],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return {
        "snapshot_id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        "schema_version": MAJOR_SHAREHOLDER_SNAPSHOT_SCHEMA_VERSION,
        "ticker": ticker,
        "as_of_date": as_of_date,
        "source_name": source_name,
        "record_origin": record_origin,
        "source_reference": source_reference,
        "fetched_at": next(iter(fetched_at_values)),
        "record_count": len(records),
        "status": DONE,
        "is_complete": 1,
    }


def validate_major_shareholder_snapshot(
    snapshot: Mapping[str, Any], records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate the strict contract required before absence can mean disappearance."""
    if snapshot.get("is_complete") != 1:
        return {"eligible": False, "reason": "incomplete_snapshot"}
    if snapshot.get("record_origin") != "api":
        return {"eligible": False, "reason": "manual_only_snapshot"}
    if snapshot.get("status") != DONE:
        return {"eligible": False, "reason": "invalid_snapshot_status"}
    as_of_date = _strict_date_string(snapshot.get("as_of_date"))
    if as_of_date is None:
        return {"eligible": False, "reason": "invalid_snapshot_date"}
    if not records:
        return {"eligible": False, "reason": "empty_snapshot"}

    expected_scope = (
        snapshot.get("ticker"),
        snapshot.get("source_name"),
        snapshot.get("record_origin"),
        snapshot.get("source_reference"),
    )
    identities: set[str] = set()
    for record in records:
        if record.get("record_origin") != "api":
            return {"eligible": False, "reason": "mixed_scope"}
        if _snapshot_scope(record) != expected_scope:
            return {"eligible": False, "reason": "mixed_scope"}
        if _strict_date_string(record.get("as_of_date")) != as_of_date:
            return {"eligible": False, "reason": "invalid_record_date"}
        if record.get("reconciliation_status") == "conflict_preserved":
            return {"eligible": False, "reason": "conflict_preserved"}
        identity = record.get("normalized_holder_name")
        if not identity or identity in identities:
            return {"eligible": False, "reason": "invalid_holder_identity"}
        identities.add(identity)
    return {"eligible": True, "reason": "eligible"}


def calculate_major_shareholder_delta(
    previous_snapshot: Mapping[str, Any],
    previous_records: Sequence[Mapping[str, Any]],
    current_snapshot: Mapping[str, Any],
    current_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Calculate non-inferred holder deltas for two already-selected consecutive snapshots."""
    previous_valid = validate_major_shareholder_snapshot(previous_snapshot, previous_records)
    if not previous_valid["eligible"]:
        return {"status": "ineligible_snapshot", "reason": f"previous_{previous_valid['reason']}", "changes": []}
    current_valid = validate_major_shareholder_snapshot(current_snapshot, current_records)
    if not current_valid["eligible"]:
        return {"status": "ineligible_snapshot", "reason": f"current_{current_valid['reason']}", "changes": []}

    if previous_snapshot.get("ticker") != current_snapshot.get("ticker"):
        return {"status": "incomparable_ticker", "reason": "ticker_mismatch", "changes": []}
    previous_scope = tuple(previous_snapshot.get(key) for key in ("source_name", "record_origin", "source_reference"))
    current_scope = tuple(current_snapshot.get(key) for key in ("source_name", "record_origin", "source_reference"))
    if previous_scope != current_scope:
        return {"status": "incomparable_source_scope", "reason": "source_scope_mismatch", "changes": []}
    if previous_snapshot["as_of_date"] >= current_snapshot["as_of_date"]:
        return {"status": "ineligible_snapshot", "reason": "invalid_snapshot_order", "changes": []}

    previous_by_holder = {record["normalized_holder_name"]: record for record in previous_records}
    current_by_holder = {record["normalized_holder_name"]: record for record in current_records}
    changes: list[dict[str, Any]] = []
    for holder in sorted(set(previous_by_holder) | set(current_by_holder)):
        before = previous_by_holder.get(holder)
        after = current_by_holder.get(holder)
        if before is None:
            changes.append({
                "change_type": "new_holder", "normalized_holder_name": holder,
                "holder_name_before": None, "holder_name_after": after.get("holder_name"),
                "shares_before": None, "shares_after": after.get("shares"), "shares_delta": None,
                "ownership_pct_before": None, "ownership_pct_after": after.get("ownership_pct"),
                "ownership_pct_delta": None, "shares_changed": False, "ownership_pct_changed": False,
            })
            continue
        if after is None:
            changes.append({
                "change_type": "disappeared_holder", "normalized_holder_name": holder,
                "holder_name_before": before.get("holder_name"), "holder_name_after": None,
                "shares_before": before.get("shares"), "shares_after": None, "shares_delta": None,
                "ownership_pct_before": before.get("ownership_pct"), "ownership_pct_after": None,
                "ownership_pct_delta": None, "shares_changed": False, "ownership_pct_changed": False,
            })
            continue
        before_shares, after_shares = before.get("shares"), after.get("shares")
        before_pct, after_pct = before.get("ownership_pct"), after.get("ownership_pct")
        shares_changed = before_shares is not None and after_shares is not None and before_shares != after_shares
        ownership_pct_changed = before_pct is not None and after_pct is not None and before_pct != after_pct
        if shares_changed or ownership_pct_changed:
            changes.append({
                "change_type": "changed", "normalized_holder_name": holder,
                "holder_name_before": before.get("holder_name"), "holder_name_after": after.get("holder_name"),
                "shares_before": before_shares, "shares_after": after_shares,
                "shares_delta": after_shares - before_shares if shares_changed else None,
                "ownership_pct_before": before_pct, "ownership_pct_after": after_pct,
                "ownership_pct_delta": after_pct - before_pct if ownership_pct_changed else None,
                "shares_changed": shares_changed, "ownership_pct_changed": ownership_pct_changed,
            })
    return {
        "status": "ok",
        "reason": "comparable_complete_snapshots",
        "from_snapshot_id": previous_snapshot.get("snapshot_id"),
        "to_snapshot_id": current_snapshot.get("snapshot_id"),
        "changes": changes,
    }


def evaluate_freshness(records: Sequence[ShareholderRecord], threshold_days: int, today: date | None = None) -> dict[str, Any]:
    latest = max((record.as_of_date for record in records if record.as_of_date), default=None)
    if latest is None:
        return {"status": "unknown", "threshold_days": threshold_days, "age_days": None, "latest_as_of_date": None}
    reference = today or date.today()
    age_days = (reference - date.fromisoformat(latest)).days
    return {
        "status": STALE if age_days > threshold_days else "fresh",
        "threshold_days": threshold_days,
        "age_days": age_days,
        "latest_as_of_date": latest,
    }


def build_shareholder_summary(
    chain: SourceChainResult,
    manual_records: Sequence[ShareholderRecord] = (),
    *,
    freshness_threshold_days: int = 180,
    today: date | None = None,
) -> dict[str, Any]:
    combined = deduplicate_records([*chain.records, *manual_records])
    freshness = evaluate_freshness(combined, freshness_threshold_days, today=today)
    if manual_records:
        status, reason = MANUAL_OVERRIDE, "verified_manual_records_merged_without_deleting_api_records"
    elif combined and freshness["status"] == STALE:
        status, reason = STALE, "latest_shareholder_as_of_date_exceeds_freshness_threshold"
    elif combined:
        status, reason = DONE, chain.reason
    else:
        status, reason = chain.final_status, chain.reason
    return {
        "ticker": chain.ticker,
        "status": status,
        "reason": reason,
        "attempts": [attempt.to_dict() for attempt in chain.attempts],
        "raw_record_count": chain.raw_record_count,
        "parsed_record_count": chain.parsed_record_count,
        "deduplicated_record_count": len(combined),
        "major_shareholders_count": len(combined) if combined else None,
        "manual_override_count": len(manual_records),
        "latest_as_of_date": freshness["latest_as_of_date"],
        "freshness": freshness,
        "records": [record.to_dict() for record in combined],
    }


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    sources = config.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("shareholder config requires a non-empty sources list")
    threshold = int(config.get("freshness_threshold_days", 180))
    if threshold <= 0:
        raise ValueError("freshness_threshold_days must be positive")
    return {**config, "freshness_threshold_days": threshold}
