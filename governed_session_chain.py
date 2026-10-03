"""Known-at calendar coverage and one future prospective session-counting contract.

Calendar projections are never completed observations. Disjoint source windows and
overlapping disagreements break continuity; no weekday or price-file fallback.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any, Mapping

import prospective_market_snapshot_contract as market

CONTRACT_VERSION = "governed_session_chain/v1"
CALENDAR_KIND = "dnse_working_dates_calendar_receipt"
CALENDAR_RESOLVER_VERSION = "governed_calendar_evidence_at_cutoff/v1"


def governed_calendar_evidence_at_cutoff(static_calendar=None, receipts=(), *, cutoff,
                                         scope="DNSE_SECURITIES_MARKET_EXCHANGES_UNSPECIFIED"):
    """One pure lookup projection; disjoint segments never assert gap coverage."""
    base = ()
    if static_calendar:
        from canonical_market_bars import governed_calendar_projection
        static = governed_calendar_projection(static_calendar)
        known = static.get("knowledge_available_at")
        if not known or market._utc(known, "static_known_at") <= market._utc(cutoff, "cutoff"):
            base = static["sessions"]
    coverage = CalendarCoverage(receipts, cutoff=cutoff, base_sessions=base,
        base_identity=static["artifact_identity"] if base else None,
        base_known_at=static.get("knowledge_available_at") if base else None,
        base_source=static["source"] if base else None)
    if scope != "DNSE_SECURITIES_MARKET_EXCHANGES_UNSPECIFIED":
        # DNSE's existing receipt cannot establish an exchange-specific calendar.
        coverage = CalendarCoverage((), cutoff=cutoff)
    segments = [{**p, "sessions": list(p["sessions"])} for p in coverage.components]
    gaps = [{"after": a["end"], "before": b["start"], "state": "UNSUPPORTED_CALENDAR_GAP"}
            for a, b in zip(segments, segments[1:])]
    body = {"contract_version": CALENDAR_RESOLVER_VERSION, "knowledge_cutoff": cutoff,
        "source": {"scope": scope}, "sessions": sorted({d for p in segments for d in p["sessions"]}),
        "segments": segments, "unsupported_gaps": gaps, "overlap_disagreements": coverage.conflicts,
        "sources": [{**w, "sessions": sorted(w["sessions"])} for w in coverage.windows],
        "status": "SUPPORTED_SEGMENTS" if segments else "UNAVAILABLE", "authority_effect": "NONE"}
    body.update(market.content_identity(body, kind="governed_calendar_evidence_at_cutoff"))
    return body


def are_consecutive_governed_sessions(previous, current, cutoff, calendar_evidence):
    """TRUE/FALSE/UNKNOWN with exact interval provenance; no civil-day fallback."""
    date.fromisoformat(previous); date.fromisoformat(current)
    if not calendar_evidence:
        return {"state": "UNKNOWN", "reason": "CALENDAR_EVIDENCE_UNAVAILABLE", "source_identities": []}
    expected = market.content_identity(calendar_evidence, kind="governed_calendar_evidence_at_cutoff")
    if (calendar_evidence.get("contract_version") != CALENDAR_RESOLVER_VERSION or
        any(calendar_evidence.get(k) != v for k, v in expected.items()) or
        market._utc(calendar_evidence["knowledge_cutoff"], "calendar_cutoff") > market._utc(cutoff, "cutoff")):
        raise ValueError("GOVERNED_CALENDAR_PROJECTION_INVALID")
    part = next((p for p in calendar_evidence["segments"] if p["start"] <= previous <= current <= p["end"]), None)
    if (not part or previous not in part["sessions"] or current not in part["sessions"] or
        any(previous <= d <= current for c in calendar_evidence["overlap_disagreements"] for d in c["sessions"])):
        return {"state": "UNKNOWN", "reason": "UNSUPPORTED_OR_DISPUTED_CALENDAR_INTERVAL", "source_identities": []}
    days = [d for d in part["sessions"] if previous <= d <= current]
    return {"state": "TRUE" if previous < current and days == [previous, current] else "FALSE",
            "reason": None if days == [previous, current] else "INTERVENING_GOVERNED_SESSION",
            "source_identities": part["source_identities"], "sessions": days,
            "calendar_identity": calendar_evidence["artifact_identity"]}


def verified_calendar(receipt: Mapping[str, Any]) -> None:
    expected = market.content_identity(receipt, kind=CALENDAR_KIND)
    days = receipt.get("sessions", [])
    if (receipt.get("contract_version") != CALENDAR_KIND + "/v1" or
        any(receipt.get(k) != v for k, v in expected.items()) or
        receipt.get("source") != {"provider": "DNSE", "route": "/market/working-dates", "field": "workingDates",
                                  "scope": "DNSE_SECURITIES_MARKET_EXCHANGES_UNSPECIFIED"} or
        not days or days != sorted(set(days)) or receipt.get("window_start") != days[0] or
        receipt.get("window_end") != days[-1] or receipt.get("allowed_uses") != ["DNSE_FORWARD_WORKING_DATE_IDENTITY"] or
        days[0] < market._utc(receipt.get("retrieved_at"), "retrieved_at").astimezone(market.VN_TZ).date().isoformat() or
        market._utc(receipt.get("knowledge_available_at"), "calendar_known_at") !=
        max(market._utc(receipt.get("retrieved_at"), "retrieved_at"),
            market._utc(receipt.get("documentation_retrieved_at"), "documentation_retrieved_at"))):
        raise ValueError("CALENDAR_RECEIPT_INTEGRITY_INVALID")
    for day in days:
        if date.fromisoformat(day).isoformat() != day:
            raise ValueError("CALENDAR_SESSION_INVALID")


class CalendarCoverage:
    def __init__(self, receipts=(), *, cutoff: str, base_sessions=(), base_identity=None, base_known_at=None, base_source=None):
        self.cutoff = cutoff
        instant = market._utc(cutoff, "cutoff")
        windows = []
        for receipt in receipts:
            verified_calendar(receipt)
            if market._utc(receipt["knowledge_available_at"], "known_at") <= instant:
                windows.append({"start": receipt["window_start"], "end": receipt["window_end"],
                                "sessions": set(receipt["sessions"]), "identity": receipt["artifact_identity"],
                                "known_at": receipt["knowledge_available_at"], "source":receipt["source"]})
        if base_sessions:
            base = sorted(set(base_sessions))
            windows.append({"start": base[0], "end": base[-1], "sessions": set(base),
                            "identity": base_identity or "legacy_governed_calendar:" + market.sha256_hex(market.canonical(base)),
                            "known_at": base_known_at, "source":base_source})
        self.windows = sorted(windows, key=lambda w: (w["start"], w["end"], w["identity"]))
        self.conflicts = []
        # Index disagreements by exact date instead of retaining all pairwise
        # window comparisons. Identical overlapping windows add no conflict.
        all_days = sorted({d for w in self.windows for d in w["sessions"]})
        for day in all_days:
            covered = [w for w in self.windows if w["start"] <= day <= w["end"]]
            if len({day in w["sessions"] for w in covered}) > 1:
                self.conflicts.append({"state": "CALENDAR_REVISION_DISAGREEMENT", "sessions": [day],
                    "source_identities": sorted(w["identity"] for w in covered),
                    "present_in": sorted(w["identity"] for w in covered if day in w["sessions"]),
                    "absent_in": sorted(w["identity"] for w in covered if day not in w["sessions"])})
        self.conflicted_sessions = {d for c in self.conflicts for d in c["sessions"]}
        self.components = []
        for window in self.windows:
            # Only overlapping supported intervals can connect. Civil adjacency
            # is deliberately insufficient to prove absence of another session.
            if self.components and window["start"] <= self.components[-1]["end"]:
                part = self.components[-1]
                part["end"] = max(part["end"], window["end"])
                part["sessions"].update(window["sessions"])
                part["source_identities"].append(window["identity"])
            else:
                self.components.append({"start": window["start"], "end": window["end"],
                                        "sessions": set(window["sessions"]), "source_identities": [window["identity"]]})
        for part in self.components:
            part["sessions"] = sorted(part["sessions"] - self.conflicted_sessions)
            part["source_identities"] = sorted(set(part["source_identities"]))

    def component(self, session):
        return next((p for p in self.components if p["start"] <= session <= p["end"]), None)

    def supported(self, session):
        part = self.component(session)
        return bool(part and session in part["sessions"] and session not in self.conflicted_sessions)

    def connected(self, start, end):
        part = self.component(start)
        return bool(part and self.supported(start) and self.supported(end) and end <= part["end"] and
                    not any(start <= d <= end for d in self.conflicted_sessions))

    def support(self, session):
        sources = sorted(w["identity"] for w in self.windows if session in w["sessions"])
        body = {"session": session, "state": "SUPPORTED" if self.supported(session) else "UNSUPPORTED",
                "source_identities": sources, "scope": "DNSE_SECURITIES_MARKET_EXCHANGES_UNSPECIFIED"}
        body.update(market.content_identity(body, kind="prospective_calendar_support"))
        return body

    def window_ending(self, session, n):
        _positive_n(n)
        part = self.component(session)
        if not part or not self.supported(session):
            return []
        days = [d for d in part["sessions"] if d <= session]
        # A disputed omission is a barrier even though it is absent from days.
        barriers = [d for d in self.conflicted_sessions if d <= session]
        if barriers:
            days = [d for d in days if d > max(barriers)]
        return days[-n:]


def _positive_n(n):
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError("POSITIVE_SESSION_COUNT_REQUIRED")


class GovernedSessionChain(Sequence):
    """Realized completed captures with strict calendar windows and projections."""
    contract_version = CONTRACT_VERSION

    def __init__(self, records=(), *, calendar: CalendarCoverage, as_of: str, first_complete_capture_session=None):
        self.calendar, self.as_of = calendar, as_of
        self.first_complete_capture_session = first_complete_capture_session
        instant = market._utc(as_of, "as_of")
        accepted = {}
        for row in records:
            expected = market.content_identity(row, kind="prospective_capture_complete_session")
            if (row.get("contract_version") != "prospective_capture_complete_session/v1" or
                any(row.get(k) != v for k, v in expected.items()) or
                row.get("completion_gate_status") != "READY" or not row.get("completion_gate_identity") or
                not row.get("capture_binding_identity") or not row.get("listing_presence_identity") or
                not row.get("market_manifest_identity")):
                raise ValueError("CAPTURE_SESSION_INTEGRITY_INVALID")
            day = row["session"]
            if (market._utc(row["completion_known_at"], "completion_known_at") <= instant and
                first_complete_capture_session and day >= first_complete_capture_session):
                if day in accepted and accepted[day]["artifact_identity"] != row["artifact_identity"]:
                    raise ValueError("CAPTURE_SESSION_CONFLICT")
                accepted[day] = row
        self.records = accepted
        self.sessions = sorted(accepted)

    def __len__(self):
        return len(self.sessions)

    def __getitem__(self, item):
        return self.sessions[item]

    def window_ending(self, session, n):
        days = self.calendar.window_ending(session, n)
        # Stop at the first missed capture. A sparse list is never a full window.
        tail = []
        for day in reversed(days):
            if day not in self.records:
                break
            tail.append(day)
        return list(reversed(tail))

    def next_n_sessions(self, after, n, as_of=None):
        _positive_n(n)
        cutoff = market._utc(as_of or self.as_of, "as_of")
        part = self.calendar.component(after)
        days = [d for d in part["sessions"] if d > after][:n] if part and self.calendar.supported(after) else []
        disputed = any(after < d <= (days[-1] if days else after) for d in self.calendar.conflicted_sessions)
        realized = [d for d in days if d in self.records and
                    market._utc(self.records[d]["completion_known_at"], "known_at") <= cutoff]
        civil_day = cutoff.astimezone(market.VN_TZ).date().isoformat()
        missed = [d for d in days if d not in realized and d < civil_day]
        status = ("UNSUPPORTED_CALENDAR_GAP" if len(days) < n else
                  "CALENDAR_REVISION_DISAGREEMENT" if disputed else
                  "MISSED_CAPTURE" if missed else "COMPLETE" if len(realized) == n and after in self.records else "PROJECTED_ONLY")
        return {"contract_version": CONTRACT_VERSION, "after": after, "n": n, "sessions": days,
                "target": days[-1] if len(days) == n else None, "state": status,
                "realized_sessions": realized, "projected_sessions": [d for d in days if d not in realized],
                "missed_sessions": missed, "projection_is_evidence": False}

    def gaps(self):
        out = [{**c, "sessions": [d for d in c["sessions"] if self.sessions and self.sessions[0] <= d <= self.sessions[-1]]}
               for c in self.calendar.conflicts if any(self.sessions and self.sessions[0] <= d <= self.sessions[-1] for d in c["sessions"])]
        for before, after in zip(self.sessions, self.sessions[1:]):
            if not self.calendar.connected(before, after):
                out.append({"state": "UNSUPPORTED_CALENDAR_GAP", "after": before, "before": after})
            else:
                part = self.calendar.component(before)
                missed = [d for d in part["sessions"] if before < d < after and d not in self.records]
                if missed:
                    out.append({"state": "MISSED_CAPTURE", "sessions": missed, "after": before, "before": after})
        return out

    def realized_prefix_after(self, after, n, as_of=None):
        result = self.next_n_sessions(after, n, as_of=as_of)
        prefix = []
        for day in result["sessions"]:
            if day not in result["realized_sessions"] or not self.calendar.connected(after, day):
                break
            prefix.append(day)
        return prefix if after in self.records else []


def cohort_mode(session, first_complete_capture_session):
    return "GOVERNED_CAPTURE_CHAIN" if first_complete_capture_session and session >= first_complete_capture_session else "LEGACY_RETAINED_SESSION_MODE"


def registered_outcome_horizons():
    from integrated_decision_prospective_feedback import FORWARD_HORIZONS
    from prospective_decision_outcome_measurement import HORIZONS
    from prospective_daily_rollforward import HORIZONS as LEARNING_HORIZONS
    return sorted(set(FORWARD_HORIZONS.values()) | set(HORIZONS.values()) | set(LEARNING_HORIZONS.values()))
