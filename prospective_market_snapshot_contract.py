"""Provider-neutral prospective market-price snapshot contract (PROSPECTIVE_RAW_PIT_AUTHORITY_V1).

Three claims are kept apart on every snapshot and are never merged into one boolean:

* ``source_basis_claim``  -- what the SOURCE says about its own price basis (documented raw,
  documented adjusted, or UNDOCUMENTED). Never inferred from the route being official.
* ``observation``         -- what Stock Lookup can prove about WHEN it possessed the bytes: exact
  payload hash, byte length and ``knowledge_available_at``. A retained receipt proves possession
  at that time and nothing about the source's basis.
* ``revision``            -- whether the same ticker/session was ever seen to change between two
  retained receipts. ``NEVER_REVISED_OBSERVED_SAMPLE`` is scoped to the tested sample/provider/field.

Timing is classified deterministically. A bar for session S that was retained no later than the
opening of the next trading session (``PROSPECTIVE_SAME_SESSION_CAPTURE``) cannot yet have been
re-based for any later corporate action, so it is the as-traded bar for S *as known then*. The same
row retained days later is ``RETROSPECTIVE_ACQUISITION``: its bytes are still hashed at a known time
(future revisions become detectable) but it earns no prospective authority.

This module computes no adjustment, fabricates no price and grants no execution or backtest
authority. It only evaluates use-specific fitness for retained snapshots.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence

CONTRACT_VERSION = "prospective_market_snapshot/v1"
SCHEMA_VERSION = "1.0.0"
VN_TZ = timezone(timedelta(hours=7))
SESSION_CLOSE_VN = "15:00:00"
NEXT_SESSION_OPEN_VN = "09:00:00"

# Source basis claim vocabulary (what the source says).
SOURCE_DOCUMENTS_RAW = "SOURCE_DOCUMENTS_RAW"
SOURCE_DOCUMENTS_ADJUSTED = "SOURCE_DOCUMENTS_ADJUSTED"
SOURCE_BASIS_UNDOCUMENTED = "SOURCE_BASIS_UNDOCUMENTED"
SOURCE_CLAIMS = frozenset({SOURCE_DOCUMENTS_RAW, SOURCE_DOCUMENTS_ADJUSTED, SOURCE_BASIS_UNDOCUMENTED})

# Empirical basis test vocabulary (what a retained test showed, always scoped).
EMPIRICAL_NOT_TESTED = "EMPIRICAL_NOT_TESTED"
EMPIRICAL_UNADJUSTED_ACROSS_EVENT = "EMPIRICAL_UNADJUSTED_ACROSS_EVENT"
EMPIRICAL_ADJUSTED_ACROSS_EVENT = "EMPIRICAL_ADJUSTED_ACROSS_EVENT"
EMPIRICAL_INCONCLUSIVE = "EMPIRICAL_INCONCLUSIVE"

# Capture timing.
PROSPECTIVE_SAME_SESSION_CAPTURE = "PROSPECTIVE_SAME_SESSION_CAPTURE"
RETROSPECTIVE_ACQUISITION = "RETROSPECTIVE_ACQUISITION"
CAPTURE_TIMING_UNKNOWN = "CAPTURE_TIMING_UNKNOWN"

# Revision classes.
NEVER_REVISED_OBSERVED_SAMPLE = "NEVER_REVISED_OBSERVED_SAMPLE"
REVISED_RETROSPECTIVELY = "REVISED_RETROSPECTIVELY"
NO_COMPARABLE_SNAPSHOT = "NO_COMPARABLE_SNAPSHOT"
SOURCE_BASIS_UNKNOWN = "SOURCE_BASIS_UNKNOWN"
REVISION_CLASSES = frozenset({NEVER_REVISED_OBSERVED_SAMPLE, REVISED_RETROSPECTIVELY, NO_COMPARABLE_SNAPSHOT, SOURCE_BASIS_UNKNOWN})

# Use-specific allowed uses (never one RAW/PIT boolean).
USE_CURRENT_SESSION_PRICE_RESEARCH = "CURRENT_SESSION_PRICE_RESEARCH"
USE_PROSPECTIVE_AS_KNOWN_PRICE_EVIDENCE = "PROSPECTIVE_AS_KNOWN_PRICE_EVIDENCE"
USE_PROSPECTIVE_RAW_AS_TRADED_PRICE = "PROSPECTIVE_RAW_AS_TRADED_PRICE"
USE_REVISION_DETECTION_BASELINE = "REVISION_DETECTION_BASELINE"
ALL_USES = (USE_CURRENT_SESSION_PRICE_RESEARCH, USE_PROSPECTIVE_AS_KNOWN_PRICE_EVIDENCE,
            USE_PROSPECTIVE_RAW_AS_TRADED_PRICE, USE_REVISION_DETECTION_BASELINE)
#: Uses this contract can never grant, regardless of snapshot content.
NEVER_GRANTED = ("HISTORICAL_RAW_AS_TRADED_PRICE", "POINT_IN_TIME_ADJUSTED_HISTORY", "PIT_BACKTEST_ELIGIBILITY",
                 "EXECUTION_REPLAY_ELIGIBILITY")

_SENSITIVE_KEY_PARTS = ("token", "secret", "password", "apikey", "api_key", "api-key", "authorization",
                        "signature", "cookie", "credential", "otp")


class SnapshotContractError(ValueError):
    """The supplied snapshot input is invalid; nothing is retained."""


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_identity(value: Mapping[str, Any], *, kind: str) -> dict[str, str]:
    body = {k: v for k, v in value.items() if k not in {"artifact_sha256", "artifact_identity", "snapshot_identity"}}
    digest = sha256_hex(canonical(body))
    return {"artifact_sha256": digest, "artifact_identity": f"{kind}:{digest}"}


def _utc(value: datetime | str, name: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise SnapshotContractError(f"{name}_not_iso8601") from error
    if value.tzinfo is None or value.utcoffset() is None:
        raise SnapshotContractError(f"{name}_timezone_required")
    return value.astimezone(timezone.utc)


def _reject_secrets(value: Any, path: str = "snapshot") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if item and any(part in str(key).lower() for part in _SENSITIVE_KEY_PARTS):
                raise SnapshotContractError(f"secret_shaped_field_rejected:{path}.{key}")
            _reject_secrets(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_secrets(item, f"{path}[{index}]")


def capture_timing(session: str, receipt_at: datetime | str, *, next_session: str | None) -> tuple[str, list[str]]:
    """Classify a receipt against the session it describes.

    Prospective only when the receipt is at/after the session close (15:00 Vietnam) AND strictly
    before the next trading session opens (09:00 Vietnam). ``next_session`` must come from the
    governed calendar; without it the classification is conservative (``CAPTURE_TIMING_UNKNOWN``).
    """
    received = _utc(receipt_at, "receipt_at")
    close = datetime.fromisoformat(f"{session}T{SESSION_CLOSE_VN}").replace(tzinfo=VN_TZ).astimezone(timezone.utc)
    if received < close:
        return RETROSPECTIVE_ACQUISITION, ["RECEIPT_BEFORE_SESSION_CLOSE_INCOMPLETE_BAR_NOT_PROSPECTIVE_CLOSED"]
    # No session can open before 09:00 Vietnam on the next CALENDAR day, so a receipt before that instant
    # is provably before the next session opened even when the calendar has no later session yet.
    earliest_next_open = (datetime.fromisoformat(f"{session}T{NEXT_SESSION_OPEN_VN}").replace(tzinfo=VN_TZ)
                          + timedelta(days=1)).astimezone(timezone.utc)
    if received < earliest_next_open:
        return PROSPECTIVE_SAME_SESSION_CAPTURE, []
    if next_session is None:
        return CAPTURE_TIMING_UNKNOWN, ["NEXT_TRADING_SESSION_UNRESOLVED"]
    opens = datetime.fromisoformat(f"{next_session}T{NEXT_SESSION_OPEN_VN}").replace(tzinfo=VN_TZ).astimezone(timezone.utc)
    if received < opens:
        return PROSPECTIVE_SAME_SESSION_CAPTURE, []
    return RETROSPECTIVE_ACQUISITION, ["RECEIPT_AFTER_NEXT_SESSION_OPEN_LATER_EVENTS_MAY_HAVE_REBASED_SOURCE"]


def allowed_uses(*, timing: str, source_claim: str, empirical: str, cross_source_agreement: bool | None,
                 parsed_ok: bool, has_price: bool) -> tuple[list[str], list[str]]:
    """Use-specific fitness. Returns (allowed_uses, reason_codes for withheld uses)."""
    uses: list[str] = []
    reasons: list[str] = []
    if not (parsed_ok and has_price):
        return [], ["SNAPSHOT_NOT_PARSED_OR_NO_TRADED_PRICE"]
    uses.append(USE_REVISION_DETECTION_BASELINE)  # any hashed known-time receipt can anchor a later revision test
    prospective = timing == PROSPECTIVE_SAME_SESSION_CAPTURE
    if prospective:
        uses += [USE_CURRENT_SESSION_PRICE_RESEARCH, USE_PROSPECTIVE_AS_KNOWN_PRICE_EVIDENCE]
    else:
        reasons.append("NOT_PROSPECTIVE_SAME_SESSION_CAPTURE")
    if source_claim == SOURCE_DOCUMENTS_ADJUSTED or empirical == EMPIRICAL_ADJUSTED_ACROSS_EVENT:
        reasons.append("SOURCE_BASIS_ADJUSTED_NOT_RAW")
    elif not prospective:
        reasons.append("RAW_AS_TRADED_REQUIRES_PROSPECTIVE_CAPTURE")
    elif cross_source_agreement is not True:
        reasons.append("RAW_AS_TRADED_REQUIRES_INDEPENDENT_CROSS_SOURCE_AGREEMENT")
    else:
        # Latest closed bar retained before any later session could re-base it, agreed by an
        # independent source, and not shown or claimed to be adjusted: as-traded for S as known then.
        uses.append(USE_PROSPECTIVE_RAW_AS_TRADED_PRICE)
    return uses, reasons


def build_snapshot(*, provider: str, source_id: str, route: str, ticker: str, exchange: str | None, session: str,
                   receipt_at: datetime | str, payload_sha256: str, payload_bytes: int, payload_hash_kind: str,
                   next_session: str | None, ohlc: Mapping[str, Any] | None, volume_value: Mapping[str, Any] | None = None,
                   board_basis: Mapping[str, Any] | None = None, source_claim: str = SOURCE_BASIS_UNDOCUMENTED,
                   empirical: str = EMPIRICAL_NOT_TESTED, cross_source_agreement: bool | None = None,
                   payload_observed_at: str | int | None = None, source_corporate_action_state: str | None = None,
                   parsed_ok: bool = True) -> dict[str, Any]:
    """One immutable, content-identified snapshot record (no I/O, no clock reads)."""
    if source_claim not in SOURCE_CLAIMS:
        raise SnapshotContractError("source_claim_unsupported")
    if not ticker or not session or not provider or not source_id:
        raise SnapshotContractError("identity_fields_required")
    try:
        date.fromisoformat(session)
    except ValueError as error:
        raise SnapshotContractError("session_not_iso_date") from error
    if len(payload_sha256) != 64 or payload_bytes <= 0:
        raise SnapshotContractError("payload_hash_and_length_required")
    received = _utc(receipt_at, "receipt_at")
    ohlc_fields = {key: (ohlc or {}).get(key) for key in ("open", "high", "low", "close", "average")}
    has_price = all(isinstance(ohlc_fields[k], (int, float)) and ohlc_fields[k] > 0 for k in ("open", "high", "low", "close"))
    timing, timing_reasons = capture_timing(session, received, next_session=next_session)
    uses, withheld = allowed_uses(timing=timing, source_claim=source_claim, empirical=empirical,
                                  cross_source_agreement=cross_source_agreement, parsed_ok=parsed_ok, has_price=has_price)
    record = {
        "contract_version": CONTRACT_VERSION, "schema_version": SCHEMA_VERSION,
        "instrument": {"ticker": ticker.upper(), "exchange": exchange},
        "trading_session": session,
        "source": {"provider": provider, "source_id": source_id, "route": route},
        "acquisition": {"receipt_at_utc": received.isoformat().replace("+00:00", "Z"),
                        "payload_observed_at": payload_observed_at,
                        "knowledge_available_at_utc": received.isoformat().replace("+00:00", "Z"),
                        "capture_timing": timing, "capture_timing_reasons": timing_reasons},
        "payload": {"sha256": payload_sha256, "bytes": payload_bytes, "hash_kind": payload_hash_kind},
        "normalized": {"ohlc": ohlc_fields, "volume_value": dict(volume_value or {}), "has_traded_price": has_price},
        "board_basis": dict(board_basis or {}),
        "basis": {"source_basis_claim": source_claim, "empirical_basis_test": empirical,
                  "source_corporate_action_state": source_corporate_action_state,
                  "adjusted_raw_unknown_claim": ("adjusted" if source_claim == SOURCE_DOCUMENTS_ADJUSTED else
                                                 "raw" if source_claim == SOURCE_DOCUMENTS_RAW else "unknown")},
        "observation": {"possession_at_known_time_proven": True,
                        "prospectively_observed": timing == PROSPECTIVE_SAME_SESSION_CAPTURE,
                        "never_revised_proven": False,
                        "cross_source_agreement": cross_source_agreement},
        "qualification": {"state": ("PROSPECTIVE_QUALIFIED" if USE_PROSPECTIVE_AS_KNOWN_PRICE_EVIDENCE in uses else
                                    "RETAINED_KNOWN_TIME_BASELINE_ONLY" if uses else "NOT_QUALIFIED"),
                          "allowed_uses": uses, "withheld_reason_codes": sorted(set(withheld)),
                          "never_granted_by_this_contract": list(NEVER_GRANTED)},
    }
    _reject_secrets(record)
    digest = sha256_hex(canonical(record))
    record["snapshot_identity"] = f"{CONTRACT_VERSION}:{digest}"
    return record


def revision_classification(t0: Mapping[str, Any] | None, t1: Mapping[str, Any] | None) -> dict[str, Any]:
    """Compare two snapshots of the SAME ticker/session/provider/route retained at different known times."""
    if t0 is None or t1 is None:
        return {"classification": NO_COMPARABLE_SNAPSHOT, "reason": "MISSING_T0_OR_T1"}
    keys = [("instrument", "ticker"), ("trading_session",), ("source", "provider"), ("source", "route")]
    def pick(rec, path):
        for part in path:
            rec = rec[part]
        return rec
    if any(pick(t0, k) != pick(t1, k) for k in keys):
        return {"classification": NO_COMPARABLE_SNAPSHOT, "reason": "IDENTITY_MISMATCH"}
    if t1["acquisition"]["receipt_at_utc"] <= t0["acquisition"]["receipt_at_utc"]:
        return {"classification": NO_COMPARABLE_SNAPSHOT, "reason": "T1_NOT_AFTER_T0"}
    if t0["basis"]["source_basis_claim"] == SOURCE_BASIS_UNDOCUMENTED and t0["basis"]["empirical_basis_test"] == EMPIRICAL_NOT_TESTED \
            and t0["normalized"]["ohlc"] != t1["normalized"]["ohlc"]:
        # A change is still a change; only equality under an unknown basis is weak evidence.
        pass
    changed = [k for k in ("open", "high", "low", "close") if t0["normalized"]["ohlc"][k] != t1["normalized"]["ohlc"][k]]
    span_hours = round((datetime.fromisoformat(t1["acquisition"]["receipt_at_utc"].replace("Z", "+00:00"))
                        - datetime.fromisoformat(t0["acquisition"]["receipt_at_utc"].replace("Z", "+00:00"))).total_seconds() / 3600, 3)
    if changed:
        return {"classification": REVISED_RETROSPECTIVELY, "changed_fields": changed, "interval_hours": span_hours}
    same_bytes = t0["payload"]["sha256"] == t1["payload"]["sha256"]
    return {"classification": NEVER_REVISED_OBSERVED_SAMPLE, "changed_fields": [], "interval_hours": span_hours,
            "identical_payload_hash": same_bytes,
            "scope": "tested ticker/session/provider/route and O/H/L/C only; not generalised"}


def summarize(snapshots: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Counts only: safe for public manifests (no per-ticker price values)."""
    rows = list(snapshots)
    return {
        "snapshots": len(rows),
        "by_capture_timing": dict(sorted(Counter(r["acquisition"]["capture_timing"] for r in rows).items())),
        "by_qualification_state": dict(sorted(Counter(r["qualification"]["state"] for r in rows).items())),
        "by_allowed_use": dict(sorted(Counter(u for r in rows for u in r["qualification"]["allowed_uses"]).items())),
        "by_source_basis_claim": dict(sorted(Counter(r["basis"]["source_basis_claim"] for r in rows).items())),
        "by_empirical_basis_test": dict(sorted(Counter(r["basis"]["empirical_basis_test"] for r in rows).items())),
        "withheld_reason_counts": dict(sorted(Counter(c for r in rows for c in r["qualification"]["withheld_reason_codes"]).items())),
    }


SESSION_MANIFEST_KIND = "prospective_market_snapshot_session_manifest"


def build_session_manifest(exact_session_snapshot: Mapping[str, Any], *, session: str, next_session: str | None = None,
                           official_series: Mapping[str, Sequence[float]] | None = None) -> dict[str, Any]:
    """Session receipt manifest from a Daily exact-session snapshot (component-local, offline, no I/O).

    Every ticker whose target-session bar carries a ``retrieved_at`` becomes one hashed, known-time
    snapshot. ``official_series`` (ticker -> O/H/L/C in the same unit) is the optional independent
    cross-source; without it no bar earns PROSPECTIVE_RAW_AS_TRADED_PRICE and raw fitness stays withheld.
    A snapshot for another session, or a missing/naive receipt time, is never substituted.
    """
    declared = exact_session_snapshot.get("resolved_completed_session") or exact_session_snapshot.get("target_session")
    if declared != session:
        raise SnapshotContractError("snapshot_session_mismatch")
    records = []
    skipped: Counter = Counter()
    for ticker, record in sorted((exact_session_snapshot.get("records") or {}).items()):
        bar = next((o for o in (record.get("observations") or []) if o.get("session") == session), None)
        if bar is None:
            skipped["NO_TARGET_SESSION_OBSERVATION"] += 1
            continue
        if not bar.get("retrieved_at"):
            skipped["NO_RECEIPT_TIME"] += 1
            continue
        payload = canonical({"ticker": ticker, "session": session, "open": bar["open"], "high": bar["high"], "low": bar["low"],
                             "close": bar["close"], "volume": bar.get("volume"), "retrieved_at": bar["retrieved_at"]})
        official = (official_series or {}).get(ticker)
        agreement = None if official is None else all(abs(float(x) - float(bar[k])) < 1e-6 for x, k in zip(official, ("open", "high", "low", "close")))
        try:
            records.append(build_snapshot(
                provider=str(bar.get("provider") or "DNSE"), source_id=str(bar.get("dataset") or "DNSE_OHLC_1D"), route="/price/ohlc",
                ticker=ticker, exchange=None, session=session, receipt_at=bar["retrieved_at"], payload_sha256=sha256_hex(payload),
                payload_bytes=len(payload), payload_hash_kind="canonical_json_of_retained_observation", next_session=next_session,
                ohlc={k: bar[k] for k in ("open", "high", "low", "close")}, volume_value={"volume": bar.get("volume")},
                board_basis={"unit": bar.get("price_unit"), "price_basis_label": bar.get("price_basis")},
                source_claim=SOURCE_BASIS_UNDOCUMENTED, cross_source_agreement=agreement))
        except SnapshotContractError as error:
            skipped[f"INVALID:{error}"] += 1
    manifest = {
        "contract_version": SESSION_MANIFEST_KIND + "/v1", "schema_version": SCHEMA_VERSION, "session": session,
        "source_snapshot_identity": exact_session_snapshot.get("snapshot_identity"),
        "summary": summarize(records), "skipped": dict(sorted(skipped.items())),
        "snapshot_identities": [r["snapshot_identity"] for r in records],
        "records": records,
        "authority_boundary": {"raw_as_traded_requires_independent_cross_source": True, "pit_backtest": "BLOCKED",
                               "execution_replay": "BLOCKED", "raw_bodies_published": False},
    }
    manifest.update(content_identity(manifest, kind=SESSION_MANIFEST_KIND))
    return manifest
