"""Daily I/O boundary for existing prospective market, universe and CA contracts.

No clock, acquisition, historical membership reconstruction or authority registry.
Receipt identity binds source/session/retrieval time; content changes at that same
receipt are corruption, while later observations retain an explicit previous version.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

from atomic_io import retain_immutable_bytes
import prospective_market_snapshot_contract as market

CONTRACT_VERSION = "prospective_market_evidence_retention/v1"


def retain_working_dates_calendar(raw_bytes: bytes, *, retrieved_at: str, documentation_sha256: str,
                                 documentation_retrieved_at: str, root: Path) -> dict:
    from completed_market_session_gate import build_working_dates_calendar_receipt
    receipt = build_working_dates_calendar_receipt(raw_bytes, retrieved_at=retrieved_at,
        documentation_sha256=documentation_sha256, documentation_retrieved_at=documentation_retrieved_at)
    directory = root / "operations-review" / "prospective-calendar-evidence-v1"
    retain_immutable_bytes(directory / "raw" / receipt["payload_sha256"], raw_bytes)
    path = directory / "receipts" / (receipt["artifact_sha256"] + ".json")
    _retain(path, receipt)
    return {"path": str(path), "artifact_identity": receipt["artifact_identity"],
            "session_count": len(receipt["sessions"]), "window_start": receipt["window_start"], "window_end": receipt["window_end"]}


def _retain(path: Path, value: Mapping[str, Any]) -> bool:
    return retain_immutable_bytes(path, market.canonical(value))


def _verified(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    expected = market.content_identity(value, kind="prospective_market_receipt")
    if value.get("artifact_identity") != expected["artifact_identity"]:
        raise ValueError("RETAINED_RECEIPT_IDENTITY_MISMATCH")
    if path.name != value["receipt_id"] + ".json":
        raise ValueError("RETAINED_RECEIPT_PATH_MISMATCH")
    if path.read_bytes() != market.canonical(value):
        raise ValueError("RETAINED_RECEIPT_BYTES_MISMATCH")
    return value


def retain_market(exact_snapshot: Mapping[str, Any], *, session: str, root: Path,
                  official_series: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    manifest = market.build_session_manifest(exact_snapshot, session=session, official_series=official_series)
    directory = root / "operations-review" / "prospective-market-evidence-v1" / session
    receipts = directory / "receipts"
    # Bounded to this exact session, never a recursive retained-source search.
    prior = [_verified(p) for p in sorted(receipts.glob("*.json"))]
    prior_by_id = {p["receipt_id"]: p for p in prior}
    prior_by_series = defaultdict(list)
    for p in prior:
        prior_by_series[market.canonical(p["series_key"])].append(p)
    identities = []
    for observation in manifest["records"]:
        key = {"instrument": observation["instrument"], "source": observation["source"], "session": session}
        known = observation["acquisition"]["knowledge_available_at_utc"]
        receipt_id = market.sha256_hex(market.canonical({**key, "known_at": known}))
        path = receipts / (receipt_id + ".json")
        matching = prior_by_id.get(receipt_id)
        if matching:
            if matching["observation"] != observation:
                raise ValueError("IMMUTABLE_RECEIPT_OBSERVATION_CONFLICT")
            _retain(path, matching)
            retained = matching
        else:
            predecessors = [p for p in prior_by_series[market.canonical(key)] if
                            p["observation"]["acquisition"]["knowledge_available_at_utc"] < known]
            previous = max(predecessors, key=lambda p: (p["observation"]["acquisition"]["knowledge_available_at_utc"], p["receipt_id"]), default=None)
            retained = {"contract_version": CONTRACT_VERSION, "receipt_id": receipt_id, "series_key": key,
                "observation": observation, "previous_version_identity": previous["artifact_identity"] if previous else None,
                "revision": market.revision_classification(previous["observation"] if previous else None, observation),
                "volume_changed": previous["observation"]["normalized"]["volume_value"] != observation["normalized"]["volume_value"] if previous else None}
            retained.update(market.content_identity(retained, kind="prospective_market_receipt"))
            _retain(path, retained)
        identities.append(retained["artifact_identity"])
    manifest["receipt_version_identities"] = identities
    manifest.update(market.content_identity(manifest, kind=market.SESSION_MANIFEST_KIND))
    path = directory / "manifests" / (manifest["artifact_sha256"] + ".json")
    reused = _retain(path, manifest)
    return {"status": "ALREADY_RETAINED_IDENTICAL" if reused else "RETAINED", "path": str(path),
            "artifact_identity": manifest["artifact_identity"], "summary": manifest["summary"], "skipped": manifest["skipped"]}


def retain_universe(source_path: Path, *, root: Path) -> dict[str, Any]:
    from current_official_market_universe import verify_retained_artifact
    from current_official_universe_evidence_retention import retain_evidence
    artifact = json.loads(source_path.read_bytes())
    verify_retained_artifact(artifact, label="PROSPECTIVE_UNIVERSE")
    directory = root / "operations-review" / "prospective-universe-evidence-v1" / artifact["artifact_sha256"]
    destination = directory / "source.json"
    # Reuse existing source contract and retainer; independently enforce exact-byte immutability.
    if destination.exists() and destination.read_bytes() != source_path.read_bytes():
        raise ValueError("IMMUTABLE_UNIVERSE_SOURCE_CONFLICT")
    retain_evidence(source_path=source_path, destination_path=destination, expected_identity=artifact["artifact_identity"])
    rows = []
    for ticker, row in sorted(artifact.get("records", {}).items()):
        observed = row.get("official_observed_at")
        if observed:
            market._utc(observed, "official_observed_at")
        rows.append({"ticker": ticker, "source_observation": row, "knowledge_available_at": observed,
                     "active_universe_at_time": "UNKNOWN",
                     "reason_codes": ["CURRENT_EXCHANGE_PRESENCE_NOT_ACTIVE_MEMBERSHIP_AT_TIME"]})
    projection = {"contract_version": CONTRACT_VERSION, "source_identity": artifact["artifact_identity"],
                  "records": rows, "active_membership_qualified": 0, "historical_backfill": False}
    projection.update(market.content_identity(projection, kind="prospective_universe_observations"))
    _retain(directory / "observations.json", projection)
    return {"status": "RETAINED", "path": str(directory / "observations.json"), "artifact_identity": projection["artifact_identity"],
            "observations": len(rows), "source_observations_with_known_time": sum(bool(r["knowledge_available_at"] and r["source_observation"].get("official_source_row_identity")) for r in rows),
            "active_membership_qualified": 0}


def retain_selected_listing_sources(source_root: Path, *, acquisition_session: str, root: Path) -> dict[str, Any]:
    """Retain NEW listing observations from A's exact verified acquisition.

    The static current universe can lack HNX receipt timestamps. Never assign its
    rows a new time: preserve the separately acquired HNX/HOSE source observations.
    Existing source bridge and universe row semantics own normalization.
    """
    from official_corporate_event_incremental_acquisition import verify_successful_acquisition, _hnx_bridge
    from current_official_market_universe import _source_row, _observed_by_source
    verified = verify_successful_acquisition(source_root, acquisition_session)
    sources = {"hnx":_hnx_bridge(verified["hnx"]),"hose":verified["hose"]}
    records = []
    for source, dataset, family in (("hnx","hnx_official_equity_universe/v1","HNX_UPCOM"), ("hose","hose_public_stock_master/v1","HOSE")):
        artifact = sources[source]
        observed = _observed_by_source(artifact)
        for raw in artifact.get("datasets",{}).get(dataset,[]):
            known = observed.get(str(raw.get("source_identity")))
            if known:
                market._utc(known,"listing_receipt_at")
            normalized = _source_row(row=raw,source=family,observed_at=known)
            records.append({"source_observation":raw,"current_universe_projection":normalized,
                "knowledge_available_at":known,"active_universe_at_time":"UNKNOWN",
                "reason_codes":["CURRENT_EXCHANGE_PRESENCE_NOT_ACTIVE_MEMBERSHIP_AT_TIME"]})
    value = {"contract_version":CONTRACT_VERSION,"acquisition_attempt_identity":verified["attempt_identity"],
             "source_artifacts":sources,"records":records,"active_membership_qualified":0,"historical_backfill":False}
    value.update(market.content_identity(value,kind="prospective_listing_source_observations"))
    path = root / "operations-review/prospective-universe-evidence-v1/listing-sources" / (value["artifact_sha256"]+".json")
    _retain(path,value)
    return {"status":"RETAINED","path":str(path),"artifact_identity":value["artifact_identity"],"observations":len(records),
            "source_observations_with_known_time":sum(bool(r["knowledge_available_at"]) for r in records),"active_membership_qualified":0}


def retain_corporate(context: Mapping[str, Any], *, root: Path,
                     ledger: Mapping[str, Any] | None = None) -> dict[str, Any]:
    from current_official_event_context import replay
    from official_corporate_action_ledger import build_ledger
    from qualified_corporate_action_factor_chain import build_factor_chain_entry
    replay(context)
    # Index observations are not typed official-document terms. Never convert them into ledger terms.
    canonical_ledger = ledger if ledger is not None else build_ledger([])
    entries = {e["event_id"]: e for e in canonical_ledger.get("entries", [])}
    events = list(context.get("all_current_universe_event_records", [])) + list(context.get("excluded_noncurrent_or_official_only_event_records", []))
    rows = []
    for event in events:
        observed = event.get("official_observed_at")
        if observed:
            market._utc(observed, "official_observed_at")
        published = event.get("published_at")
        if published:
            market._utc(published, "published_at")
        entry = entries.get(event.get("source_event_id"))
        cutoff = max((observed, published), key=lambda t: market._utc(t, "knowledge")) if observed and published else None
        factor = build_factor_chain_entry(entry or {}, knowledge_cutoff=cutoff)
        rows.append({"source_observation": event, "source_event_id": event.get("source_event_id"),
                     "source_record_identity": event.get("source_record_identity"),
                     "knowledge_available_at": cutoff or observed, "published_at": published,
                     "terms": {k: event.get(k) for k in ("ratio", "cash_amount", "terms", "effective_date", "payment_date")},
                     "factor_chain": factor,
                     "version_identity": event.get("event_id"),
                     "correction_of": event.get("correction_of"),
                     "limitations": ["SOURCE_RECORD_ID_IS_NOT_STABLE_EVENT_ID", "CALENDAR_IS_NOT_EXECUTED_LIFECYCLE"] if not entry else []})
    artifact = {"contract_version": CONTRACT_VERSION, "source_context": context, "records": rows,
                "qualified_factor_count": sum(r["factor_chain"]["status"] == "QUALIFIED" for r in rows)}
    artifact.update(market.content_identity(artifact, kind="prospective_corporate_observations"))
    path = root / "operations-review" / "prospective-corporate-evidence-v1" / (artifact["artifact_sha256"] + ".json")
    _retain(path, artifact)
    return {"status": "RETAINED", "path": str(path), "artifact_identity": artifact["artifact_identity"],
            "observations": len(rows), "qualified_factor_count": artifact["qualified_factor_count"]}


def attempt(component, *args, **kwargs) -> dict[str, Any]:
    """Component-local failure blocks only dependent prospective use."""
    try:
        return component(*args, **kwargs)
    except Exception as exc:
        return {"status": "UNAVAILABLE", "reason": f"{type(exc).__name__}:{exc}"}
