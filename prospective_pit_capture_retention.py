"""Bounded offline I/O for compact capture batches and once-per-Daily readiness.

One session record and write-once marker start the future clock. This module never
fetches a provider, modifies an old receipt, or treats a run manifest as completion.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from atomic_io import retain_immutable_bytes
from governed_session_chain import CalendarCoverage, GovernedSessionChain, registered_outcome_horizons
import prospective_market_evidence_retention as retention
import prospective_market_snapshot_contract as market
import prospective_pit_capture as capture

STORE = "operations-review/prospective-pit-capture-v1"
DEPTHS = (20, 21, 50, 60, 120, 250)
# Exact already-retained first-party schema receipt from the October 2 closure.
# No new documentation request and no date inferred from repository modification time.
WORKING_DATES_DOCUMENTATION = {
    "sha256": "7ffc05d537f8f6bc982dbf8108960e6c6eb5337482710b4309d189919fb40858",
    "known_at": "2026-10-02T03:40:02.445723+00:00",
}


def io_known_at():
    """Actual evidence I/O boundary clock; pure builders receive this explicitly."""
    return datetime.now(timezone.utc).isoformat()


def _read(path):
    return json.loads(Path(path).read_bytes())


def _retain_batch(root, family, value):
    path = Path(root) / STORE / family / value["session"] / (value["artifact_sha256"] + ".json")
    retention._retain(path, value)
    return {"status": "RETAINED", "path": str(path), "artifact_identity": value["artifact_identity"],
            "records": len(value["records"])}


def retain_existing_calendar_probe(evidence, *, root):
    """Accept only an actual exact raw response + actual I/O timestamp.

    An injected normalized gate/dates list does not create a source receipt.
    """
    if not isinstance(evidence, dict) or not isinstance(evidence.get("raw_bytes"), bytes) or not evidence.get("retrieved_at"):
        return {"status": "NOT_CAPTURED", "reason": "EXACT_EXISTING_PROBE_BYTES_OR_TIME_ABSENT"}
    result = retention.retain_working_dates_calendar(evidence["raw_bytes"], retrieved_at=evidence["retrieved_at"],
        documentation_sha256=WORKING_DATES_DOCUMENTATION["sha256"],
        documentation_retrieved_at=WORKING_DATES_DOCUMENTATION["known_at"], root=Path(root))
    receipt = _read(result["path"])
    coverage = CalendarCoverage(load_calendars(root), cutoff=receipt["knowledge_available_at"])
    revision = capture.identified({"contract_version": "prospective_calendar_revision/v1",
        "receipt_identity": receipt["artifact_identity"], "known_at": receipt["knowledge_available_at"],
        "overlap_disagreements": coverage.conflicts, "authority_effect": "NONE"}, "prospective_calendar_revision")
    retention._retain(Path(root) / STORE / "calendar-revisions" / (revision["artifact_sha256"] + ".json"), revision)
    return {**result, "status": "RETAINED", "revision_identity": revision["artifact_identity"],
            "overlap_disagreement_count": len(coverage.conflicts)}


def load_calendars(root):
    directory = Path(root) / "operations-review/prospective-calendar-evidence-v1"
    rows = []
    for path in sorted((directory / "receipts").glob("*.json")):
        value = _read(path)
        from governed_session_chain import verified_calendar
        verified_calendar(value)
        if path.stem != value["artifact_sha256"]: raise ValueError("CALENDAR_RECEIPT_PATH_MISMATCH")
        raw = directory / "raw" / value["payload_sha256"]
        # Bounded source body (normally ~257 dates), no date-only fabrication.
        body = raw.read_bytes()
        if hashlib.sha256(body).hexdigest() != value["payload_sha256"] or len(body) != value["payload_bytes"]:
            raise ValueError("CALENDAR_RAW_BYTES_MISMATCH")
        if json.loads(body).get("workingDates") != value["sessions"]:
            raise ValueError("CALENDAR_RAW_DATES_MISMATCH")
        rows.append(value)
    return rows


def calendar_evidence_at_cutoff(root, *, cutoff, static_path=None):
    from governed_session_chain import governed_calendar_evidence_at_cutoff
    static_path = Path(static_path) if static_path else Path(root) / "config/governed_trading_session_calendar_v1.json"
    static = _read(static_path) if static_path.exists() else None
    return governed_calendar_evidence_at_cutoff(static, load_calendars(root), cutoff=cutoff)


def load_marker(root):
    path = Path(root) / STORE / "first_complete_capture_session.json"
    if not path.exists():
        return None
    value = capture.verify(_read(path), "first_complete_capture_session")
    record_path = Path(root) / STORE / "sessions" / (value["session"] + ".json")
    record = capture.verify(_read(record_path), "prospective_capture_complete_session")
    if record["artifact_identity"] != value["capture_session_identity"]:
        raise ValueError("FIRST_CAPTURE_MARKER_BINDING_MISMATCH")
    return value


def _load_batch_ref(ref, contract):
    value = capture.verify(_read(ref["path"]), contract + ":batch")
    if value["artifact_identity"] != ref["artifact_identity"] or value["contract_version"] != contract:
        raise ValueError("CAPTURE_BATCH_REFERENCE_MISMATCH")
    for row in value["records"]:
        capture.verify(row, contract)
    return value


def listing_batch(evidence, *, session, root, created_at):
    rows = []
    ref = evidence.get("listing_sources") or {}
    if ref.get("path"):
        source = _read(ref["path"])
        capture.verify(source, "prospective_listing_source_observations")
        if source["artifact_identity"] != ref["artifact_identity"]:
            raise ValueError("LISTING_SOURCE_REFERENCE_MISMATCH")
        for record in source["records"]:
            projection = record["current_universe_projection"]
            rows.append(capture.listing_presence(projection, session=session,
                source_artifact_identity=source["artifact_identity"], source_row=record["source_observation"]))
    elif (evidence.get("universe") or {}).get("path"):
        ref = evidence["universe"]
        source = capture.verify(_read(ref["path"]), "prospective_universe_observations")
        if source["artifact_identity"] != ref["artifact_identity"]:
            raise ValueError("UNIVERSE_SOURCE_REFERENCE_MISMATCH")
        rows = [capture.listing_presence(r["source_observation"], session=session,
                source_artifact_identity=source["source_identity"]) for r in source["records"]]
    value = capture.batch(capture.LISTING_CONTRACT, rows, session=session, created_at=created_at)
    return value, _retain_batch(root, "listing", value)


def _previous_bindings(root, session, cutoff):
    # Read only the latest completed prior session's compact batch, once.
    paths = [p for p in (Path(root) / STORE / "sessions").glob("*.json") if p.stem < session]
    if not paths:
        return {}
    record = capture.verify(_read(max(paths)), "prospective_capture_complete_session")
    if market._utc(record["completion_known_at"], "known_at") > market._utc(cutoff, "cutoff"):
        return {}
    value = _load_batch_ref(record["capture_binding"], capture.CAPTURE_CONTRACT)
    return {r["ticker"]: r for r in value["records"]}


def retain_capture_bindings(snapshot, *, session, evidence, root, created_at, next_session=None):
    if session < capture.CAPTURE_START_NOT_BEFORE:
        return {"status": "LEGACY_CAPTURE_INCOMPLETE", "reason": "PRE_RELEASE_SESSION_NO_RECONSTRUCTION"}
    existing = Path(root) / STORE / "sessions" / (session + ".json")
    if existing.exists():
        record = capture.verify(_read(existing), "prospective_capture_complete_session")
        _load_batch_ref(record["capture_binding"], capture.CAPTURE_CONTRACT)
        _load_batch_ref(record["listing_presence"], capture.LISTING_CONTRACT)
        return {"status": "ALREADY_CAPTURED", "capture_binding": record["capture_binding"],
                "listing_presence": record["listing_presence"], "original_completion_known_at": record["completion_known_at"]}
    market_ref = evidence.get("market") or {}
    if not market_ref.get("path"):
        return {"status": "INCOMPLETE_CAPTURE", "reason": "MARKET_MANIFEST_UNAVAILABLE"}
    manifest = capture.verify(_read(market_ref["path"]), market.SESSION_MANIFEST_KIND)
    if manifest["artifact_identity"] != market_ref["artifact_identity"] or manifest["source_snapshot_identity"] != snapshot.get("snapshot_identity"):
        raise ValueError("MARKET_MANIFEST_REFERENCE_MISMATCH")
    presence, presence_ref = listing_batch(evidence, session=session, root=root, created_at=created_at)
    by_ticker = defaultdict(list)
    for row in presence["records"]:
        by_ticker[row["ticker"]].append(row)
    prior = _previous_bindings(root, session, created_at)
    receipts_dir = Path(market_ref["path"]).parent.parent / "receipts"
    # Current-session receipt files are read once and indexed; never once per ticker.
    wanted = set(manifest["receipt_version_identities"])
    receipts = {r["artifact_identity"]: r for p in sorted(receipts_dir.glob("*.json"))
                if (r := retention._verified(p))["artifact_identity"] in wanted}
    if set(receipts) != wanted:
        raise ValueError("CAPTURE_RECEIPTS_MISSING")
    # Conservative, provable cutoff: next civil day 09:00 Vietnam. Extending a
    # window needs a separately bound calendar proof; this V1 never guesses it.
    _, close = capture.capture_window(session)
    rows = []
    for receipt in receipts.values():
        ticker = receipt["observation"]["instrument"]["ticker"]
        source_record = (snapshot.get("records") or {}).get(ticker) or {}
        bars = [r for r in source_record.get("observations", []) if r.get("session") == session]
        if len(bars) != 1:
            raise ValueError("EXACT_CAPTURE_BAR_AMBIGUOUS")
        matches = [r for r in by_ticker[ticker] if capture.qualifying_presence(r, ticker=ticker, session=session, cutoff=created_at)]
        selected = matches[0] if len({(r["exchange"], r["board"]) for r in matches}) == 1 else None
        rows.append(capture.capture_binding(receipt, bars[0], source_record, source_snapshot_identity=snapshot["snapshot_identity"],
            created_at=created_at, capture_window_close=close, presence=selected, previous=prior.get(ticker)))
    value = capture.batch(capture.CAPTURE_CONTRACT, rows, session=session, created_at=created_at,
                          market_manifest_identity=manifest["artifact_identity"], listing_presence_identity=presence["artifact_identity"])
    ref = _retain_batch(root, "bindings", value)
    return {"status": "RETAINED", "capture_binding": ref, "listing_presence": presence_ref,
            "market_manifest": market_ref, "capture_window_close": close,
            "capture_complete_tickers": sum(capture.effective_receipt(receipts[r["receipt_artifact_identity"]], [r], created_at)["capture_state"] ==
                                            "T0_CAPTURE_COMPLETE" for r in rows)}


def retained_official_rows(ledger_paths):
    """Exact operator-selected official ledgers only; no search/crawl/acquisition.

    Preserve native official numbers and exact rows. A 1000x empirical ratio
    is retained as a relation, never treated as documented economic units.
    """
    from urllib.parse import urlparse
    result = defaultdict(list)
    for ledger_path in ledger_paths:
        ledger_path = Path(ledger_path)
        with ledger_path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                entry = json.loads(line)
                url = urlparse((entry.get("request") or {}).get("url", ""))
                if entry.get("outcome") != "OK" or url.hostname != "api.hsx.vn" or url.path != "/mk/api/v1/market/securities/tradingresult":
                    continue
                raw = (ledger_path.parent / "raw" / (entry["sha256"] + ".bin")).read_bytes()
                if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
                    raise ValueError("OFFICIAL_RETAINED_BODY_HASH_MISMATCH")
                for row in json.loads(raw)["data"]["list"]:
                    session = datetime.fromtimestamp(row["reportDate"], timezone.utc).date().isoformat()
                    ticker = row["symbol"].strip().upper()
                    item = {"provider": "HOSE", "source_id": "HOSE_PUBLIC_MARKET_API_SECURITIES_TRADINGRESULT",
                            "ticker": ticker, "session": session, "exact_row": row,
                            "row_identity": "official_row:" + market.sha256_hex(market.canonical(row)),
                            "source_artifact_identity": "exact_http_response_body:" + entry["sha256"],
                            "source_artifact_sha256": entry["sha256"], "official_known_at": entry["retrieved_at"],
                            "ohlc": {k: row[f] for k, f in zip(capture.OHLC, ("openPrice", "highPrice", "lowPrice", "closePrice"))},
                            "price_unit": "UNKNOWN", "source_basis_claim": market.SOURCE_BASIS_UNDOCUMENTED}
                    result[(ticker, session)].append(item)
    return result


def retain_verifications(root, *, session, capture_ref, verification_known_at, ledger_paths=(), unavailable=False):
    value = _load_batch_ref(capture_ref, capture.CAPTURE_CONTRACT)
    official = retained_official_rows(ledger_paths)
    receipts_dir = Path(root) / "operations-review/prospective-market-evidence-v1" / session / "receipts"
    rows = []
    for binding in value["records"]:
        receipt = retention._verified(receipts_dir / (binding["receipt_id"] + ".json"))
        matches = [r for r in official.get((binding["ticker"], session), []) if
                   market._utc(r["official_known_at"], "official_known_at") <= market._utc(verification_known_at, "known_at")]
        for row in matches or [None]:
            rows.append(capture.official_verification(binding, receipt["observation"], row,
                verification_known_at=verification_known_at, unavailable=unavailable))
    batch = capture.batch(capture.VERIFICATION_CONTRACT, rows, session=session, created_at=verification_known_at)
    return _retain_batch(root, "verifications", batch)


def retain_registered_verifications(root, *, session, capture_result, verification_known_at, registry_root=None):
    """Normal Daily reuses explicit exact operator selections; no newest search.

    Registry entries may name earlier post-release sessions for late verification.
    Current-session absence stays pending. Historical receipts are not backfilled.
    """
    registry_root = Path(registry_root or root)
    path = registry_root / "config/prospective_market_official_verification_registry.json"
    registry = _read(path) if path.exists() else {}
    targets = dict(registry.get("sessions") or {})
    if capture_result.get("capture_binding"):
        targets.setdefault(session, [])
    results = {}
    for day, selected in sorted(targets.items()):
        if day < capture.CAPTURE_START_NOT_BEFORE or day > session:
            continue
        if day == session and capture_result.get("capture_binding"):
            ref = capture_result["capture_binding"]
        else:
            record_path = Path(root) / STORE / "sessions" / (day + ".json")
            if not record_path.exists():
                continue
            ref = capture.verify(_read(record_path), "prospective_capture_complete_session")["capture_binding"]
        # Do not accumulate identical pending evidence on owner resume.
        if not selected and any((Path(root) / STORE / "verifications" / day).glob("*.json")):
            continue
        ledgers = [registry_root / item for item in selected]
        results[day] = retain_verifications(root, session=day, capture_ref=ref,
            verification_known_at=verification_known_at, ledger_paths=ledgers)
    return {"status": "RETAINED" if results else "NO_NEW_VERIFICATION", "sessions": results,
            "new_provider_requests": 0}


def load_chain(root, *, as_of):
    marker = load_marker(root)
    records = [capture.verify(_read(p), "prospective_capture_complete_session") for p in
               sorted((Path(root) / STORE / "sessions").glob("*.json"))]
    return GovernedSessionChain(records, calendar=CalendarCoverage(load_calendars(root), cutoff=as_of),
        as_of=as_of, first_complete_capture_session=marker["session"] if marker else None)


def verify_complete_session(root, value):
    """Reverify original evidence at original completion time, never rerun time."""
    capture.verify(value, "prospective_capture_complete_session")
    session, known = value["session"], value["completion_known_at"]
    if session < capture.CAPTURE_START_NOT_BEFORE or value.get("completion_gate_status") != "READY":
        raise ValueError("RECOVERY_COMPLETE_READY_REQUIRED")
    coverage = CalendarCoverage(load_calendars(root), cutoff=known)
    support = coverage.support(session)
    if support["state"] != "SUPPORTED" or support != value["calendar_support"]:
        raise ValueError("RECOVERY_CALENDAR_SUPPORT_INVALID")
    binding = _load_batch_ref(value["capture_binding"], capture.CAPTURE_CONTRACT)
    listing = _load_batch_ref(value["listing_presence"], capture.LISTING_CONTRACT)
    manifest = capture.verify(_read(value["market_manifest"]["path"]), market.SESSION_MANIFEST_KIND)
    if (manifest["artifact_identity"] != value["market_manifest_identity"] or
        value["market_manifest"]["artifact_identity"] != manifest["artifact_identity"] or
        binding["artifact_identity"] != value["capture_binding_identity"] or
        listing["artifact_identity"] != value["listing_presence_identity"] or
        binding["listing_presence_identity"] != listing["artifact_identity"] or
        binding["market_manifest_identity"] != manifest["artifact_identity"] or
        any(v["session"] != session or market._utc(v["created_at"], "created_at") > market._utc(known, "completion_known_at") for v in (binding, listing))):
        raise ValueError("RECOVERY_BATCH_BINDING_INVALID")
    receipts = {r["artifact_identity"]: r for p in (Path(value["market_manifest"]["path"]).parent.parent / "receipts").glob("*.json")
                if (r := retention._verified(p))["artifact_identity"] in manifest["receipt_version_identities"]}
    if set(receipts) != set(manifest["receipt_version_identities"]): raise ValueError("RECOVERY_RECEIPTS_MISSING")
    complete = 0
    for row in binding["records"]:
        receipt = receipts.get(row["receipt_artifact_identity"])
        if not receipt or row["source_snapshot_identity"] != value["t0_market_snapshot_identity"]:
            raise ValueError("RECOVERY_SOURCE_BINDING_INVALID")
        if market._utc(known, "known") >= market._utc(row["capture_window_close"], "close"):
            raise ValueError("RECOVERY_CAPTURE_WINDOW_INVALID")
        if capture.effective_receipt(receipt, [row], known)["capture_state"] == "T0_CAPTURE_COMPLETE":
            matches = [p for p in listing["records"] if p["artifact_identity"] == row["listing_observation_identity"] and
                       capture.qualifying_presence(p, ticker=row["ticker"], session=session, cutoff=known)]
            if len(matches) != 1: raise ValueError("RECOVERY_LISTING_BINDING_INVALID")
            complete += 1
    if not complete or complete != value["capture_complete_tickers"]:
        raise ValueError("RECOVERY_CAPTURE_INCOMPLETE")
    if value.get("completion_gate"):
        g = value["completion_gate"]
        from completed_market_session_gate import stable_id
        digest = stable_id({k: v for k, v in g.items() if k not in {"gate_identity", "gate_content_identity"}})
        if (g.get("gate_identity") != "completed_market_session_gate:"+digest or
            g.get("gate_content_identity") != digest or g["gate_identity"] != value["completion_gate_identity"] or
            g.get("completion_gate_status") != "READY" or g.get("resolved_session") != session or
            g.get("exact_session_evidence", {}).get("identity") != value["t0_market_snapshot_identity"]):
            raise ValueError("RECOVERY_GATE_INVALID")
    return value


def publish_first_marker(root, value):
    verify_complete_session(root, value)
    marker_path = Path(root) / STORE / "first_complete_capture_session.json"
    existing = load_marker(root)
    if existing:
        verify_complete_session(root, _read(Path(root) / STORE / "sessions" / (existing["session"]+".json")))
        if existing["session"] > value["session"] or (existing["session"] == value["session"] and
            existing["capture_session_identity"] != value["artifact_identity"]):
            raise ValueError("FIRST_CAPTURE_MARKER_CONFLICT")
        return "ALREADY_PUBLISHED"
    for path in (Path(root) / STORE / "sessions").glob("*.json"):
        if path.stem < value["session"]:
            prior = verify_complete_session(root, _read(path))
            if prior["session"] < value["session"]: raise ValueError("EARLIER_COMPLETE_SESSION_EXISTS")
    marker = capture.identified({"contract_version": "first_complete_capture_session/v1", "session": value["session"],
        "written_at": value["completion_known_at"], "capture_session_identity": value["artifact_identity"],
        "policy": "WRITE_ONCE_FIRST_SUCCESSFUL_POST_RELEASE_COMPLETE_CAPTURE", "authority_effect": "NONE"}, "first_complete_capture_session")
    retention._retain(marker_path, marker)
    load_marker(root)
    return "PUBLISHED"


def complete_capture_session(root, *, session, gate, evidence, completion_known_at, t0_snapshot_identity=None):
    """Publish only a genuinely Phase-B READY, supported, in-window capture."""
    target = Path(root) / STORE / "sessions" / (session + ".json")
    if target.exists():
        value = verify_complete_session(root, _read(target))
        if t0_snapshot_identity is not None and t0_snapshot_identity != value.get("t0_decision_snapshot_identity"):
            raise ValueError("RECOVERY_T0_BINDING_MISMATCH")
        marker_status = publish_first_marker(root, value)
        return {"status": "ALREADY_CAPTURED", "path": str(target), "artifact_identity": value["artifact_identity"], "marker_status": marker_status}
    ref = evidence.get("capture") or {}
    if (session < capture.CAPTURE_START_NOT_BEFORE or gate.get("completion_gate_status") != "READY" or
        gate.get("resolved_session") != session or not gate.get("gate_identity") or
        ref.get("status") != "RETAINED" or not ref.get("capture_complete_tickers")):
        return {"status": "INCOMPLETE_CAPTURE", "reason": "READY_COMPLETE_CAPTURE_REQUIRED"}
    from completed_market_session_gate import stable_id
    expected_gate = stable_id({k: v for k, v in gate.items() if k not in {"gate_identity", "gate_content_identity"}})
    if gate.get("gate_identity") != "completed_market_session_gate:" + expected_gate or gate.get("gate_content_identity") != expected_gate:
        raise ValueError("CAPTURE_COMPLETION_GATE_IDENTITY_INVALID")
    if market._utc(completion_known_at, "completion_known_at") >= market._utc(ref["capture_window_close"], "window_close"):
        return {"status": "LATE_NOT_T0_QUALIFIED", "reason": "CAPTURE_WINDOW_CLOSED"}
    coverage = CalendarCoverage(load_calendars(root), cutoff=completion_known_at)
    support = coverage.support(session)
    if support["state"] != "SUPPORTED":
        return {"status": "INCOMPLETE_CAPTURE", "reason": "CALENDAR_SUPPORT_UNAVAILABLE"}
    binding = _load_batch_ref(ref["capture_binding"], capture.CAPTURE_CONTRACT)
    listing = _load_batch_ref(ref["listing_presence"], capture.LISTING_CONTRACT)
    if binding["listing_presence_identity"] != listing["artifact_identity"]:
        raise ValueError("CAPTURE_LISTING_BATCH_MISMATCH")
    if (market._utc(binding["created_at"], "binding_known_at") > market._utc(completion_known_at, "completion_known_at") or
        market._utc(listing["created_at"], "listing_known_at") > market._utc(completion_known_at, "completion_known_at") or
        any(r["source_snapshot_identity"] != gate.get("exact_session_evidence", {}).get("identity") for r in binding["records"])):
        raise ValueError("CAPTURE_GATE_SOURCE_OR_TIME_MISMATCH")
    value = capture.identified({"contract_version": "prospective_capture_complete_session/v1", "session": session,
        "completion_known_at": completion_known_at, "completion_gate_identity": gate["gate_identity"], "completion_gate_status": "READY",
        "completion_gate": dict(gate),
        "calendar_support_identity": support["artifact_identity"], "calendar_support": support,
        "market_manifest_identity": ref["market_manifest"]["artifact_identity"], "market_manifest": ref["market_manifest"],
        "capture_binding_identity": binding["artifact_identity"], "capture_binding": ref["capture_binding"],
        "listing_presence_identity": listing["artifact_identity"], "listing_presence": ref["listing_presence"],
        "t0_market_snapshot_identity": binding["records"][0]["source_snapshot_identity"] if binding["records"] else None,
        "t0_decision_snapshot_identity": t0_snapshot_identity,
        "exact_session_coverage": gate.get("exact_session_evidence"),
        "capture_complete_tickers": ref["capture_complete_tickers"], "authority_effect": "NONE / CAPTURE_COMPLETENESS_ONLY"},
        "prospective_capture_complete_session")
    retention._retain(target, value)
    marker_status = publish_first_marker(root, value)
    return {"status": "RETAINED", "path": str(target), "artifact_identity": value["artifact_identity"], "marker_status": marker_status}


class CaptureIndex:
    """One run-scoped scan; retain at most 250 session bindings per ticker.

    Counts cover the whole compact capture corpus. Full OHLC receipt versions
    are loaded only for the latest day's RAW state, not per ticker/window.
    """
    def __init__(self, root, *, cutoff):
        self.root, self.cutoff = Path(root), cutoff
        self.chain = load_chain(root, as_of=cutoff)
        self.rows = defaultdict(dict)
        self.verifications = defaultdict(list)
        self.mismatch_receipts = set()
        self.scans = Counter()
        self.legacy_count = 0
        legacy_end = self.chain.first_complete_capture_session or capture.CAPTURE_START_NOT_BEFORE
        for directory in (self.root / "operations-review/prospective-market-evidence-v1").glob("*"):
            if directory.name < legacy_end and directory.is_dir():
                self.legacy_count += sum(1 for _ in (directory / "receipts").glob("*.json"))
        for session in self.chain.sessions[-max(DEPTHS):]:
            record = self.chain.records[session]
            value = _load_batch_ref(record["capture_binding"], capture.CAPTURE_CONTRACT)
            self.scans["capture_batches"] += 1
            for row in value["records"]:
                # History needs just lineage/fitness fields, not the complete
                # provenance descriptor duplicated for 250 sessions per ticker.
                self.rows[row["ticker"]][session] = row if session == self.chain.sessions[-1] else {
                    k: row[k] for k in ("ticker", "session", "exchange", "listing_binding_class", "representation_tier",
                                       "representation_fingerprint", "receipt_artifact_identity")}
        # Every retained mismatch remains counted, including sessions older than
        # the rolling depth bound and capture-incomplete names. One batch at a
        # time keeps their full exact official rows out of the long-lived index.
        for path in sorted((self.root / STORE / "verifications").glob("*/*.json")):
            session = path.parent.name
            value = capture.verify(_read(path), capture.VERIFICATION_CONTRACT + ":batch")
            self.scans["verification_batches"] += 1
            for row in value["records"]:
                capture.verify(row, capture.VERIFICATION_CONTRACT)
                if market._utc(row["verification_known_at"], "known_at") <= market._utc(cutoff, "cutoff"):
                    if row["state"] == "VERIFIED_MISMATCH":
                        self.mismatch_receipts.add(row["t0_receipt_identity"])
                    if self.chain.sessions and session == self.chain.sessions[-1]:
                        self.verifications[row["t0_receipt_identity"]].append(row)

    def readiness(self, *, session, capture_pending=False):
        latest = self.chain.sessions[-1] if self.chain.sessions else None
        expected = self.chain.window_ending(latest, max(DEPTHS)) if latest else []
        tickers, exclusions = {}, Counter()
        exchange_counts, tiers, verification_counts, uses = Counter(), Counter(), Counter(), Counter()
        depth_counts, listing_counts = Counter(), Counter()
        scans = Counter(self.scans)
        for ticker, observations in sorted(self.rows.items()):
            depth, listed_depth = 0, 0
            fingerprint = None
            for day in reversed(expected):
                row = observations.get(day)
                if not row or row["listing_binding_class"] != "SAME_SESSION_POSITIVE":
                    break
                listed_depth += 1
            for day in reversed(expected):
                row = observations.get(day)
                if not row:
                    exclusions["MISSING_EXACT_SESSION_CAPTURE"] += 1
                    break
                reason = ("SAME_SESSION_LISTING_AND_EXCHANGE_UNAVAILABLE" if row["listing_binding_class"] != "SAME_SESSION_POSITIVE" else
                          "PRICE_REPRESENTATION_UNAVAILABLE" if row["representation_tier"] == capture.UNKNOWN else
                          "SERIES_REPRESENTATION_CHANGED" if fingerprint and fingerprint != row["representation_fingerprint"] else None)
                if reason:
                    exclusions[reason] += 1
                    break
                fingerprint = row["representation_fingerprint"]
                depth += 1
            newest = observations.get(latest)
            raw = None
            if newest:
                receipt_path = self.root / "operations-review/prospective-market-evidence-v1" / latest / "receipts" / (newest["receipt_id"] + ".json")
                receipt = retention._verified(receipt_path)
                scans["latest_receipts"] += 1
                effective = capture.effective_receipt(receipt, [newest], self.cutoff)
                raw = capture.raw_use_state(effective, self.verifications[receipt["artifact_identity"]], cutoff=self.cutoff)
                exchange_counts[newest["exchange"]] += 1
                tiers[newest["representation_tier"]] += 1
                verification_counts[raw["official_match_status"]] += 1
                uses.update(raw["allowed_uses"])
            for n in DEPTHS:
                depth_counts[str(n)] += depth >= n
                listing_counts[str(n)] += listed_depth >= n
            tickers[ticker] = {"contiguous_capture_depth": depth, "positive_listing_depth": listed_depth,
                "exchange": newest["exchange"] if newest else "UNKNOWN", "representation_tier": newest["representation_tier"] if newest else capture.UNKNOWN,
                "raw_use_state": raw, "ca_comparability": "UNKNOWN / QUALIFIED_FACTOR_CHAIN_OR_NO_APPLICABLE_CA_PROOF_REQUIRED",
                "pit_component_readiness": {"observed_price_and_membership": depth >= min(DEPTHS),
                                           "continuous_price": False, "standing_vnm_signal": False}}
        horizons = registered_outcome_horizons()
        calendar_anchor = latest or session
        projected = self.chain.next_n_sessions(calendar_anchor, max(horizons)) if self.chain.calendar.supported(calendar_anchor) else None
        latest_window = max((w for w in self.chain.calendar.windows if w["known_at"]),
                            key=lambda w: market._utc(w["known_at"], "known_at"), default=None)
        latest_covers = bool(latest_window and calendar_anchor in latest_window["sessions"] and
                             len([d for d in latest_window["sessions"] if d > calendar_anchor]) >= max(horizons))
        if latest:
            exclusions["CA_COMPARABILITY_UNQUALIFIED"] += len(tickers)
        state = "NOT_CAPTURED" if not latest else "DEPTH_PENDING"
        if capture_pending and session not in self.chain.sessions:
            state = "CAPTURING"
        # Single-bar components can mature without promoting continuous-return,
        # standing signal, backtest, RAW or execution authority.
        if depth_counts[str(min(DEPTHS))] and not self.chain.gaps() and latest_covers and projected and projected["state"] not in {
            "UNSUPPORTED_CALENDAR_GAP", "CALENDAR_REVISION_DISAGREEMENT", "MISSED_CAPTURE"}:
            state = "READY_FOR_BOUNDED_EVALUATION"
        body = {"contract_version": "prospective_pit_readiness/v1", "as_of": self.cutoff, "session": session, "status": state,
            "first_complete_capture_session": self.chain.first_complete_capture_session,
            "prospective_complete_sessions": self.chain.sessions, "complete_session_count": len(self.chain),
            "session_chain_contract": self.chain.contract_version, "session_chain_gaps": self.chain.gaps(),
            "per_ticker": tickers, "counts_at_depth": {str(n): depth_counts[str(n)] for n in DEPTHS},
            "listing_counts_at_depth": {str(n): listing_counts[str(n)] for n in DEPTHS},
            "exchange_binding_counts": dict(sorted(exchange_counts.items())), "representation_tier_counts": dict(sorted(tiers.items())),
            "official_verification_state_counts": dict(sorted(verification_counts.items())), "retained_mismatch_receipts": len(self.mismatch_receipts),
            "raw_use_eligibility_counts": dict(sorted(uses.items())), "ca_blockers": ["PIT_CA_NOT_QUALIFIED", "EVENT_INDEX_NOT_FACTOR_CHAIN"],
            "future_ca_seam": {"status": "INTEGRATION_SEAM_ONLY", "blocker": "STABLE_EVENT_ID_AND_LINKED_TERMS_LIFECYCLE_KNOWLEDGE_REQUIRED",
                               "retained_contract": retention.CONTRACT_VERSION, "historical_backfill": False},
            "calendar": {"support": self.chain.calendar.support(latest) if latest else None,
                         "latest_known_window_identity": latest_window["identity"] if latest_window else None,
                         "registered_outcome_horizons": horizons, "max_registered_horizon": max(horizons),
                         "forward_projection": projected, "refresh_state": "CURRENT" if latest_covers else "CALENDAR_REFRESH_NEEDED"},
            "top_exclusion_reasons": dict(sorted(exclusions.items())), "legacy_incomplete_receipt_versions": self.legacy_count,
            "legacy_missing_components": ["CAPTURE_COMPANION", "SAME_SESSION_EXCHANGE", "PRICE_REPRESENTATION", "LISTING_PRESENCE"],
            "evaluation_authorized": False, "new_signals_declared": 0, "authority_effect": "NONE / CAPTURE_COMPLETENESS_ONLY",
            "performance": {"run_scoped_index": True, "retained_depth_per_ticker_bound": max(DEPTHS), "scans": dict(scans)}}
        return capture.identified(body, "prospective_pit_readiness")


def daily_boundary(root, *, session, gate, evidence, known_at, t0_snapshot_identity=None):
    result = complete_capture_session(root, session=session, gate=gate, evidence=evidence,
        completion_known_at=known_at, t0_snapshot_identity=t0_snapshot_identity)
    index = CaptureIndex(root, cutoff=known_at)
    readiness = index.readiness(session=session, capture_pending=session >= capture.CAPTURE_START_NOT_BEFORE and
        (evidence.get("market") or {}).get("status") in {"RETAINED", "ALREADY_RETAINED_IDENTICAL"})
    path = Path(root) / STORE / "readiness" / session / (readiness["artifact_sha256"] + ".json")
    retention._retain(path, readiness)
    return {"session_capture": result, "readiness": {"status": readiness["status"], "path": str(path),
        "artifact_identity": readiness["artifact_identity"], "complete_session_count": readiness["complete_session_count"],
        "counts_at_depth": readiness["counts_at_depth"], "authority_effect": "NONE / CAPTURE_COMPLETENESS_ONLY"}}
