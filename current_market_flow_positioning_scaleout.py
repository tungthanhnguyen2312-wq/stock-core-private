"""Deterministic retained-packet scaleout for current_market_flow_positioning/v1."""
from __future__ import annotations

import copy
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

import canonical_market_evidence_integration as canonical
from current_market_flow_positioning import build, content_identity
from field_temporal_contract import stable_id


def _read(path: Path) -> dict[str, Any]:
    import json
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise ValueError("SCALEOUT_PACKET_MALFORMED:" + str(path))
    return value


def combine_retained_packets(packet_paths: Iterable[Path], session: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Select one deterministic version per provider endpoint while retaining all versions in lineage."""
    selected: dict[tuple[str, str, str], tuple[dict[str, Any], str]] = {}
    versions: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    requestable: dict[str, set[str]] = defaultdict(set)
    source_packets: list[dict[str, Any]] = []
    for path in sorted({Path(item) for item in packet_paths}, key=lambda item: str(item)):
        packet = _read(path)
        if packet.get("session_date") != session: continue
        source_packets.append({"path": str(path), "packet_identity": packet.get("packet_identity"), "packet_sha256": packet.get("packet_sha256"), "execution_mode": packet.get("execution_mode")})
        requested_sources = set(packet.get("cli_parameters", {}).get("sources") or [])
        for symbol in packet.get("cli_parameters", {}).get("symbols") or []:
            for source in requested_sources: requestable[str(source)].add(str(symbol).upper())
        for observation in packet.get("observations") or []:
            if not isinstance(observation, Mapping) or observation.get("session") != session: continue
            item = copy.deepcopy(dict(observation)); key = (str(item.get("instrument", "")).upper(), str(item.get("source")), str(item.get("endpoint_id")))
            versions[key].append({"raw_sha256": item.get("raw_sha256"), "retrieved_at": item.get("retrieved_at") or item.get("retrieval_time"), "status": item.get("status"), "packet_identity": packet.get("packet_identity"), "path": str(path)})
            current = selected.get(key)
            rank = (item.get("status") == "ACQUIRED", str(item.get("retrieved_at") or item.get("retrieval_time") or ""), str(item.get("raw_sha256") or ""))
            if current is None or rank > (current[0].get("status") == "ACQUIRED", str(current[0].get("retrieved_at") or current[0].get("retrieval_time") or ""), str(current[0].get("raw_sha256") or "")):
                selected[key] = (item, str(path))
    observations = []
    for key, (item, _) in sorted(selected.items()):
        item["retained_version_lineage"] = sorted(versions[key], key=lambda value: (str(value.get("retrieved_at")), str(value.get("raw_sha256"))))
        observations.append(item)
    packet = {"packet_schema_version": "1.0.0", "contract_version": "current_market_flow_positioning_scaleout_retained_packet/v1", "session_date": session, "execution_mode": "RETAINED_COMPOSITE", "observations": observations, "source_packets": source_packets}
    digest = stable_id(packet); packet["packet_sha256"] = digest; packet["packet_identity"] = "retained_flow_scaleout_packet:" + digest
    report = {"source_packet_count": len(source_packets), "selected_endpoint_observations": len(observations), "retained_endpoint_versions": sum(len(value) for value in versions.values()), "provider_requestable": {source: len(symbols) for source, symbols in sorted(requestable.items())}, "requestable_symbols": {source: sorted(symbols) for source, symbols in sorted(requestable.items())}}
    return packet, report


def _cohort(records: Mapping[str, Any], tickers: Iterable[str]) -> dict[str, Any]:
    members = [str(ticker).upper() for ticker in tickers]
    rows = [records[ticker] for ticker in members if ticker in records]
    dimensions = {"any_flow_context": lambda row: row["coverage"]["available_dimensions"] > 0, "traded_value_ready": lambda row: row["traded_value"]["status"] == "AVAILABLE", "foreign_flow_ready": lambda row: row["foreign_flow"]["status"] == "AVAILABLE", "foreign_room_ready": lambda row: row["foreign_room"]["status"] == "AVAILABLE", "proprietary_ready": lambda row: row["proprietary_flow"]["status"] == "AVAILABLE", "active_order_ready": lambda row: row["active_order_context"]["status"] == "AVAILABLE", "multi_dimension_ready": lambda row: row["coverage"]["available_dimensions"] >= 2}
    reasons = Counter(status for row in rows for section in ("traded_value", "foreign_flow", "foreign_room", "proprietary_flow", "active_order_context") if (status := row[section]["status"]) != "AVAILABLE")
    return {"cohort_size": len(members), "records_present": len(rows), **{name: sum(predicate(row) for row in rows) for name, predicate in dimensions.items()}, "unavailable_reason_counts": dict(sorted(reasons.items()))}


def _intersections(flow: Mapping[str, Any], tactical: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for state in ("EARLY_REVERSAL_CANDIDATE", "BREAKOUT_READY", "UPTREND_CONFIRMED", "BASE_BUILDING", "DISTRIBUTION_RISK"):
        rows = [flow_row for ticker, flow_row in flow["records"].items() if (tactical.get("records", {}).get(ticker) or {}).get("entry_state") == state]
        result[state] = {"total": len(rows), "supportive": sum(any("CONFIRMATION" in item or "BUY_SUPPORT" in item for item in row["price_flow_relationships"]) for row in rows), "contradictory": sum(any("DIVERGENCE" in item or "SELL_PRESSURE" in item for item in row["price_flow_relationships"]) for row in rows), "unavailable": sum(row["coverage"]["available_dimensions"] == 0 for row in rows)}
    return result


def build_scaleout(*, packet_paths: Iterable[Path], session: str, candidate_tickers: Iterable[str], tactical: Mapping[str, Any], watchlist: Iterable[str], preopen_47: Iterable[str], entry_relevant_90: Iterable[str]) -> dict[str, Any]:
    packet, acquisition = combine_retained_packets(packet_paths, session)
    integration = canonical.integrate_session_packet(packet)
    flow = build(canonical_integration=integration, tactical=tactical, candidate_tickers=list(candidate_tickers))
    observations = integration.get("observations") or []
    provider_sessions = Counter((item.get("provenance") or {}).get("provider_session_date") or "SESSION_UNRESOLVED" for item in observations)
    status = Counter()
    for item in observations:
        provider_session = (item.get("provenance") or {}).get("provider_session_date")
        if provider_session is None: status["SESSION_UNRESOLVED"] += 1
        elif provider_session != session: status["SESSION_MISMATCH"] += 1
        elif item.get("observation_status") == "PROVIDER_RATE_LIMITED": status["RATE_LIMITED"] += 1
        elif item.get("observation_status") != "ACQUIRED": status["MISSING"] += 1
    reconciliation = {"traded_value": {"available": flow["coverage"]["TRADED_VALUE_READY"], "failed": sum(row["traded_value"]["status"] == "SEMANTIC_BLOCKED" for row in flow["records"].values()), "rule": "matched + put-through == total"}, "foreign_room": {"available": flow["coverage"]["FOREIGN_ROOM_READY"], "failed": sum(row["foreign_room"]["status"] == "SEMANTIC_BLOCKED" for row in flow["records"].values()), "rule": "owned + available == max"}, "foreign_flow": {"dnse_available": sum(row["foreign_flow"].get("source") == "DNSE" and row["foreign_flow"]["status"] == "AVAILABLE" for row in flow["records"].values()), "comparison": "SINGLE_SOURCE_ONLY_OR_SESSION_UNRESOLVED; no FHSC comparable semantic is selected"}}
    flow["scaleout"] = {"target_session": session, "acquisition": acquisition, "provider_session_attestation": {"provider_session_counts": dict(sorted(provider_sessions.items())), "session_status_counts": dict(sorted(status.items())), "rule": "Only provider_session_date == target session is eligible."}, "cohorts": {"watchlist_11": _cohort(flow["records"], watchlist), "preopen_47": _cohort(flow["records"], preopen_47), "entry_relevant_90": _cohort(flow["records"], entry_relevant_90)}, "reconciliation": reconciliation, "tactical_flow_intersections": _intersections(flow, tactical), "terminal_status": "COHERENT_PARTIAL_PROVIDER_LIMITED", "terminal_reason": "Retained FHSC same-session coverage is broad for traded value but all-dimension and DNSE foreign-flow coverage remain provider/request limited."}
    flow["source_artifact_identities"]["retained_composite_packet"] = packet["packet_identity"]
    flow.update(content_identity(flow)); return flow
