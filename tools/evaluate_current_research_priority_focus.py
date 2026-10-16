"""Read-only retained evaluation of the research-focus projection.

Writes only a new directory outside the source tree and the retained evidence root.
This tool qualifies Daily operations and supplies verified envelopes to the core projection.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Mapping, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import daily_opportunity_decision_queue as decision_queue
import daily_research_session_operations as operations
import next_session_decision_brief as next_session
import personal_investment_decision_action_center as action_center
from stocklookup_core.decision import bounded_research_preview as bounded
from stocklookup_core.decision import current_opportunity_prioritization as opportunity
from stocklookup_core.decision import current_research_priority_focus as focus
from stocklookup_core.decision import integrated_investment_decision_product as integrated
from stocklookup_core.evidence.bounded_json import canonical_bytes
from stocklookup_core.evidence.field_identity import stable_id

ResearchFocusError = focus.ResearchFocusError


def _load_bounded_json(path: Path) -> dict[str, Any]:
    if path.stat().st_size > focus.SOURCE_JSON_LIMIT:
        raise ResearchFocusError("SOURCE_JSON_LIMIT:" + path.name)
    with path.open(encoding="utf-8") as source:
        text = source.read(focus.SOURCE_JSON_LIMIT + 1)
    if len(text) > focus.SOURCE_JSON_LIMIT:
        raise ResearchFocusError("SOURCE_JSON_LIMIT:" + path.name)
    return json.loads(text, object_pairs_hook=bounded.strict_object, parse_constant=bounded.reject_constant,
                      parse_float=bounded.finite_float)


def _assert_lane_order(queue: Mapping[str, Any]) -> None:
    records = queue.get("records")
    lanes = queue.get("lane_queues")
    if not isinstance(records, Mapping) or not isinstance(lanes, Mapping):
        raise ResearchFocusError("QUEUE_SHAPE_INVALID")
    if set(lanes) != set(decision_queue.LANES):
        raise ResearchFocusError("QUEUE_LANE_SET_MISMATCH")
    for lane in decision_queue.LANES:
        members = [record for record in records.values()
                   if isinstance(record, Mapping) and lane in (record.get("lane_specific_priority") or {})]
        ordered = sorted(members, key=lambda record: (
            opportunity.TIERS.index(record["lane_specific_priority"][lane]), record["ticker"]))
        actual = (lanes.get(lane) or {}).get("tickers")
        if not isinstance(actual, list) or [row.get("ticker") for row in actual] != [record["ticker"] for record in ordered]:
            raise ResearchFocusError("QUEUE_LANE_ORDER_MISMATCH:" + lane)
        for row, record in zip(actual, ordered):
            if row.get("lane_priority") != record["lane_specific_priority"][lane]:
                raise ResearchFocusError("QUEUE_LANE_TIER_MISMATCH:" + lane + ":" + str(row.get("ticker")))


def _verified_queue(path: Path, *, session: str, expected_identity: str) -> dict[str, Any]:
    if not path.is_file():
        raise ResearchFocusError("QUEUE_ARTIFACT_ABSENT")
    artifact = _load_bounded_json(path)
    try:
        decision_queue.replay(artifact)
    except ValueError as exc:
        raise ResearchFocusError("QUEUE_IDENTITY_SESSION_OR_CONTRACT_MISMATCH") from exc
    if (artifact.get("contract_version") != decision_queue.CONTRACT_VERSION
            or artifact.get("research_session") != session
            or artifact.get("artifact_identity") != expected_identity
            or any(artifact.get(key) != value for key, value in decision_queue.content_identity(artifact).items())):
        raise ResearchFocusError("QUEUE_IDENTITY_SESSION_OR_CONTRACT_MISMATCH")
    _assert_lane_order(artifact)
    return artifact


def _verified_opportunity(path: Path, *, session: str, expected_identity: str) -> dict[str, Any]:
    if not path.is_file():
        raise ResearchFocusError("OPPORTUNITY_ARTIFACT_ABSENT")
    artifact = _load_bounded_json(path)
    if (artifact.get("contract_version") != opportunity.CONTRACT_VERSION
            or artifact.get("research_session") != session
            or artifact.get("artifact_identity") != expected_identity
            or any(artifact.get(key) != value for key, value in opportunity.content_identity(artifact).items())):
        raise ResearchFocusError("OPPORTUNITY_IDENTITY_SESSION_OR_CONTRACT_MISMATCH")
    return artifact


def _project(path: Path, *, session: str, expected_identity: str, full_tickers: set[str],
             slim_tickers: set[str], deadline: float) -> dict[str, Any]:
    """One native verification pass. Full objects are retained only for the dossier set."""
    before = path.stat()
    if not 0 < before.st_size <= bounded.MAX_SOURCE_BYTES:
        raise ResearchFocusError("PREVIEW_SOURCE_SIZE_REFUSED")
    full: dict[str, Any] = {}
    slim: dict[str, Any] = {}
    selected_bytes = 0
    epochs: set[str] = set()

    def consume(ticker: str, row: Mapping[str, Any]) -> None:
        nonlocal selected_bytes
        if time.monotonic() >= deadline:
            raise ValueError("ACCEPTANCE_DEADLINE_EXCEEDED")
        if not isinstance(row, dict):
            raise ValueError("PREVIEW_RECORD_INVALID:" + ticker)
        if row.get("ticker") != ticker or row.get("as_of_session") != session:
            raise ValueError("PREVIEW_RECORD_SESSION_OR_TICKER_MISMATCH:" + ticker)
        if row.get("decision_identity") != integrated.decision_identity(row):
            raise ValueError("PREVIEW_DECISION_IDENTITY_MISMATCH:" + ticker)
        integrated.validate_posture_policy(row)
        epochs.add(integrated.research_policy_epoch(row))
        if ticker in full_tickers or ticker in slim_tickers:
            slim[ticker] = focus._slim(row)
        if ticker in full_tickers:
            selected_bytes += len(canonical_bytes(row))
            if selected_bytes > bounded.MAX_SELECTED_BYTES:
                raise ValueError("PREVIEW_SELECTED_PAYLOAD_LIMIT")
            full[ticker] = row

    metadata, digest, count = bounded._stream_artifact(
        path, excluded=integrated._IDENTITY_EXCLUDED, on_record=consume, member_limit=bounded.MEMBER_LIMIT,
        metadata_limit=bounded.METADATA_LIMIT, deadline=deadline)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ResearchFocusError("PREVIEW_SOURCE_CHANGED_DURING_VERIFICATION")
    identity = f"{integrated.CONTRACT_VERSION}:{digest}"
    if (metadata.get("contract_version") != integrated.CONTRACT_VERSION or metadata.get("session") != session
            or metadata.get("schema_version") != "integrated_investment_decision_product/1.0.0"
            or metadata.get("artifact_sha256") != digest or metadata.get("artifact_identity") != identity
            or expected_identity != identity):
        raise ResearchFocusError("PREVIEW_SOURCE_CONTRACT_SESSION_OR_IDENTITY_MISMATCH")
    if epochs != {metadata.get("research_action_policy_version", "v1")}:
        raise ResearchFocusError("PREVIEW_ROOT_RECORD_POLICY_MISMATCH")
    coverage = metadata.get("coverage") or {}
    if any(coverage[key] != count for key in ("universe_denominator", "integrated_context_available") if key in coverage):
        raise ResearchFocusError("PREVIEW_SOURCE_DENOMINATOR_MISMATCH")
    return {"full": full, "slim": slim, "metadata": metadata, "source_identity": identity,
            "source_record_count": count, "source_bytes": before.st_size,
            "verification": "FULL_NATIVE_CONTENT_VERIFIED"}


def _resolve_operation(root: Path, registry: Mapping[str, Any], session: str, operation: Path, deadline: float,
                       full_tickers: set[str], slim_tickers: set[str], *, stream: bool = True) -> dict[str, Any]:
    next_session._require_qualified(registry, session)
    if registry["completed_sessions"][session].get("trading_day_valid") is not True:
        raise ResearchFocusError("PREVIEW_COMPLETED_TRADING_SESSION_NOT_QUALIFIED")
    selection = next_session.registered_session_selection(registry, session)
    locked = next_session.frozen_input_identities(registry, session)
    if {key: value["artifact_identity"] for key, value in selection.items()} != locked:
        raise ResearchFocusError("PREVIEW_COMPLETED_INPUT_LOCK_MISMATCH")
    manifest = bounded.small_json(Path(operation) / "run_manifest.json")
    expected_operation = "daily_research_session_operation:" + stable_id(
        {key: value for key, value in manifest.items() if key != "operation_identity"})
    if (manifest.get("contract_version") != operations.CONTRACT_VERSION or manifest.get("schema_version") != "1.0.0"
            or manifest.get("generation_context") != "DAILY_PRODUCER_RETAINED_COMPLETED_SESSION"
            or manifest.get("market_session") != session or manifest.get("operation_identity") != expected_operation):
        raise ResearchFocusError("PREVIEW_OPERATION_IDENTITY_OR_SESSION_MISMATCH")
    native = root / "operations-review/daily-research-session-operations-v1" / session / expected_operation.split(":")[1]
    if Path(operation).resolve() != native.resolve():
        raise ResearchFocusError("PREVIEW_UNREGISTERED_OPERATION_LOCATOR")
    manifest_inputs = manifest.get("input_artifacts") or {}
    if (set(manifest_inputs) - set(locked) - {"macro", "explicit_portfolio"}
            or {key: (manifest_inputs.get(key) or {}).get("artifact_identity") for key in locked} != locked):
        raise ResearchFocusError("PREVIEW_MANIFEST_INPUT_REFERENCE_MISMATCH")
    expected_iid = (manifest.get("outputs") or {}).get("integrated_investment_decision_product")
    if not isinstance(expected_iid, str):
        raise ResearchFocusError("PREVIEW_MANIFEST_INTEGRATED_REFERENCE_REQUIRED")
    iid_path = root / "operations-review" / ("integrated-investment-decision-product-v1-" + session.replace("-", "")) / "integrated_investment_decision_product_artifact.json"
    if stream:
        projected = _project(iid_path, session=session, expected_identity=expected_iid, full_tickers=full_tickers,
                             slim_tickers=slim_tickers, deadline=deadline)
    else:
        projected = {"full": {}, "slim": {}, "metadata": {}, "source_identity": None, "source_record_count": None,
                     "source_bytes": 0, "verification": "QUEUE_SELECTION_BEFORE_DECISION_STREAM"}
    tactical_entry = selection["tactical"]
    tactical_path = (root / tactical_entry["path"]).resolve()
    if not tactical_path.is_relative_to(root):
        raise ResearchFocusError("PREVIEW_REGISTERED_PATH_OUTSIDE_EVIDENCE_ROOT")
    from stocklookup_core.tactical import watchlist_tactical_entry_classifier as tactical_owner
    tactical = bounded.small_json(tactical_path, limit=16 * 1024 * 1024)
    if (tactical.get("session") != session or tactical.get("contract_version") != tactical_owner.CONTRACT_VERSION
            or tactical.get("artifact_identity") != tactical_entry["artifact_identity"]
            or any(tactical.get(key) != value for key, value in tactical_owner.content_identity(tactical).items())):
        raise ResearchFocusError("PREVIEW_TACTICAL_SOURCE_IDENTITY_MISMATCH")
    outputs = manifest.get("outputs") or {}
    queue_identity = outputs.get("daily_opportunity_decision_queue")
    opportunity_identity = outputs.get("opportunity_prioritization")
    queue = opportunity_artifact = None
    queue_blocker = None
    if not isinstance(queue_identity, str) or not isinstance(opportunity_identity, str):
        queue_blocker = "QUEUE_OR_OPPORTUNITY_OUTPUT_NOT_IN_OPERATION_MANIFEST"
    else:
        try:
            queue = _verified_queue(native / focus.QUEUE_FILE, session=session, expected_identity=queue_identity)
            opportunity_artifact = _verified_opportunity(native / focus.OPPORTUNITY_FILE, session=session, expected_identity=opportunity_identity)
            if queue.get("source_artifact_identities", {}).get("opportunity") != opportunity_artifact.get("artifact_identity"):
                raise ResearchFocusError("QUEUE_OPPORTUNITY_SOURCE_MISMATCH")
            if len(queue.get("records") or {}) != len(opportunity_artifact.get("records") or {}):
                raise ResearchFocusError("OPPORTUNITY_QUEUE_POPULATION_MISMATCH")
        except ResearchFocusError as exc:
            queue_blocker = str(exc)
            queue = opportunity_artifact = None
    confirmed = {ticker for ticker, row in (tactical.get("records") or {}).items()
                 if (row or {}).get("entry_state") in next_session.TACTICAL_CONFIRMATION_STATES}
    projected.update(operation_identity=expected_operation, source_locator=iid_path.relative_to(root).as_posix(),
                     tactical_identity=tactical_entry["artifact_identity"], queue=queue,
                     opportunity=opportunity_artifact, queue_blocker=queue_blocker, confirmed=confirmed,
                     queue_bytes=0 if queue is None else (native / focus.QUEUE_FILE).stat().st_size,
                     opportunity_bytes=0 if opportunity_artifact is None else (native / focus.OPPORTUNITY_FILE).stat().st_size)
    return projected


def _owner_dossier_context(*, ticker: str, decision: Mapping[str, Any], session: str,
                           current_view: Mapping[str, Any], previous_view: Mapping[str, Any] | None,
                           brief: Mapping[str, Any]) -> dict[str, Any]:
    lineage = decision.get("evidence_currency_lineage") or {}
    coverage = {ticker: lineage} if lineage.get("method") == integrated.EVIDENCE_CURRENCY_SOURCE_CONTRACT else {}
    evidence = action_center._evidence_block(ticker, decision, session=session, coverage_records=coverage)
    details = action_center._conditional_research_details(decision, evidence)
    transition = action_center._setup_transition_for_ticker(
        session=session, ticker=ticker, current_artifact=current_view, previous_artifact=previous_view, brief=brief)
    return {"evidence": evidence, "details": details, "setup_transition": transition}


def _prepare_owner_contexts(*, selection, authority, current, previous, context, session,
                            require_current_record, require_previous_record, qualified_tickers):
    dossier_contexts = {}
    labels = {}
    current_view = {**current["metadata"], "records": current["full"]}
    previous_view = None if previous is None else {**previous["metadata"], "records": previous["full"]}
    queue = current["queue"]
    opportunity_artifact = current["opportunity"]
    for item in selection["selected"]:
        ticker = item["ticker"]
        decision = current["full"].get(ticker)
        previous_row = previous["full"].get(ticker) if previous else None
        admitted = False
        if authority != "DAILY_OPPORTUNITY_DECISION_QUEUE":
            admitted = decision is not None
        else:
            queue_record = queue["records"][ticker]
            opportunity_record = opportunity_artifact["records"].get(ticker) or {}
            binding = focus._bind(queue_record, decision or current["slim"].get(ticker), opportunity_record,
                                  require_queue_record_identity=require_current_record)
            if binding["status"] == "BOUND" and decision is not None:
                admitted = True
                if previous_row is not None and previous["queue"] is not None and require_previous_record:
                    previous_queue = previous["queue"]["records"].get(ticker)
                    if previous_queue is not None and (previous_row.get("source_identities") or {}).get("priority_queue_record_identity") != previous_queue.get("content_identity"):
                        admitted = False
        if not admitted:
            continue
        if authority == "DAILY_OPPORTUNITY_DECISION_QUEUE":
            try:
                bounded.validate_price_dimensions(previous_row, decision)
            except (ResearchFocusError, ValueError):
                continue
        try:
            dossier_contexts[ticker] = _owner_dossier_context(
                ticker=ticker, decision=decision, session=session, current_view=current_view,
                previous_view=previous_view, brief=context)
        except (ResearchFocusError, action_center.ActionCenterError, ValueError) as exc:
            dossier_contexts[ticker] = {"error": exc}
    if authority == "DAILY_OPPORTUNITY_DECISION_QUEUE":
        selected_names = {item["ticker"] for item in selection["selected"]}
        for ticker in qualified_tickers:
            if ticker in selected_names:
                continue
            queue_record = queue["records"][ticker]
            opportunity_record = opportunity_artifact["records"].get(ticker) or {}
            binding = focus._bind(queue_record, current["slim"].get(ticker), opportunity_record,
                                  require_queue_record_identity=require_current_record)
            if binding["status"] == "BOUND" and current["slim"].get(ticker) is not None:
                previous_slim = previous["slim"].get(ticker) if previous else None
                labels[ticker] = action_center._expected_posture_label(
                    previous_slim, current["slim"][ticker], previous_view or {}, current_view)
    return dossier_contexts, labels


def evaluate_research_focus(*, repo_root: Path, session: str, current_operation: Path,
                            previous_operation: Path | None = None, lanes: Sequence[str] = focus.DEFAULT_LANES,
                            tiers: Sequence[str] = focus.DEFAULT_TIERS, max_tickers: int = 8,
                            include_tickers: Sequence[str] | None = None,
                            explicit_tickers_when_queue_blocked: Sequence[str] | None = None) -> dict[str, Any]:
    """Verify one current session, and the previous qualified session when the chain has one."""
    bounded.resource_gate()
    deadline = time.monotonic() + bounded.DEADLINE_SECONDS
    root = Path(repo_root).resolve()
    registry = bounded.small_json(root / "config/daily_research_session_input_registry.json")
    if registry.get("contract_version") != "daily_research_session_input_registry/v1":
        raise ResearchFocusError("PREVIEW_REGISTRY_CONTRACT_MISMATCH")
    next_session._require_qualified(registry, session)
    chain = next_session._qualified_session_chain(registry)
    prior = [date for date in chain if date < session]
    previous_session = prior[-1] if prior else None
    if (previous_session is None) != (previous_operation is None):
        raise ResearchFocusError("PREVIEW_PREVIOUS_QUALIFIED_OPERATION_REQUIRED_OR_UNEXPECTED")
    current_probe = _resolve_operation(root, registry, session, current_operation, deadline, set(), set(), stream=False)
    selection_blocker = current_probe["queue_blocker"]
    authority = "DAILY_OPPORTUNITY_DECISION_QUEUE"
    if selection_blocker is None:
        selection = focus.select_from_queue(
            current_probe["queue"], source_lanes=decision_queue.LANES, lanes=lanes, tiers=tiers,
            max_tickers=max_tickers, include_tickers=include_tickers)
        full_names = [item["ticker"] for item in selection["selected"]]
        qualified_tickers = []
        for lane in selection["lanes"]:
            for row in current_probe["queue"]["lane_queues"][lane["lane"]]["tickers"]:
                if row["lane_priority"] in tiers and (include_tickers is None or row["ticker"] in set(include_tickers)):
                    qualified_tickers.append(row["ticker"])
        qualified_tickers = list(dict.fromkeys(qualified_tickers))
    elif explicit_tickers_when_queue_blocked:
        bounded.select_tickers(explicit_tickers_when_queue_blocked)
        full_names = list(bounded.select_tickers(explicit_tickers_when_queue_blocked))
        qualified_tickers = list(full_names)
        authority = "EXPLICIT_TICKER_PREVIEW_QUEUE_BLOCKED"
        selection = {"lanes": [], "selected": [{"ticker": ticker, "primary_lane": None, "lanes": [], "lane_priority": None}
                                               for ticker in full_names], "overlaps": [], "cap_excluded": [],
                     "inclusion_exclusions": [], "queue_denominator": None, "qualified_count": None,
                     "unique_qualified_ticker_count": None, "selected_count": len(full_names)}
    else:
        raise ResearchFocusError(selection_blocker)
    full_set, slim_set = set(full_names), set(qualified_tickers)
    current = _resolve_operation(root, registry, session, current_operation, deadline, full_set, slim_set, stream=True)
    previous = None
    if previous_session is not None:
        previous = _resolve_operation(root, registry, previous_session, previous_operation, deadline, full_set, slim_set)
    current_view = {**current["metadata"], "records": current["full"]}
    previous_view = None if previous is None else {**previous["metadata"], "records": previous["full"]}
    transitions = {}
    for ticker in full_names:
        current_row = current["full"].get(ticker)
        previous_row = previous["full"].get(ticker) if previous else None
        label = action_center._expected_posture_label(previous_row, current_row, previous_view or {}, current_view) if current_row else None
        transitions[ticker] = {
            "transition": label,
            "previous_posture": None if previous_row is None else previous_row.get("research_action_posture"),
            "current_posture": None if current_row is None else current_row.get("research_action_posture"),
            "previous_decision_identity": None if previous_row is None else previous_row.get("decision_identity"),
            "current_decision_identity": None if current_row is None else current_row.get("decision_identity"),
        }
    context = {
        "current_session": session, "previous_qualified_session": previous_session,
        "posture_transition": {"records": transitions},
        "tactical_transition": {
            "availability": "AVAILABLE" if previous else "UNAVAILABLE",
            "reason_codes": [] if previous else ["NO_PREVIOUS_QUALIFIED_SESSION"],
            "gained_confirmation": sorted((current["confirmed"] & full_set) - (previous["confirmed"] if previous else set())) if previous else [],
            "retained_confirmation": sorted((current["confirmed"] & full_set) & (previous["confirmed"] if previous else set())),
            "lost_confirmation": sorted((previous["confirmed"] & full_set) - current["confirmed"]) if previous else [],
        },
        "source_lineage": {"current": current["source_identity"], "previous": previous["source_identity"] if previous else None},
    }
    context["artifact_identity"] = "selected_transition_projection:" + stable_id(context)
    current_lineage = focus._priority_lineage(current["queue"], current["metadata"])
    previous_lineage = None if previous is None else focus._priority_lineage(previous["queue"], previous["metadata"])
    require_current_record = current_lineage["status"] != "INTEGRATED_DECISION_BUILT_FROM_A_DIFFERENT_PRIORITY_QUEUE"
    require_previous_record = previous_lineage is None or previous_lineage["status"] != "INTEGRATED_DECISION_BUILT_FROM_A_DIFFERENT_PRIORITY_QUEUE"
    dossier_contexts, labels = _prepare_owner_contexts(
        selection=selection, authority=authority, current=current, previous=previous, context=context,
        session=session, require_current_record=require_current_record,
        require_previous_record=require_previous_record, qualified_tickers=qualified_tickers)
    return focus.project_research_focus(
        session=session, previous_session=previous_session, selection=selection,
        selection_authority=authority, selection_blocker=selection_blocker, current=current, previous=previous,
        transition_context=context, dossier_contexts=dossier_contexts, overview_transition_labels=labels,
        lanes=lanes, tiers=tiers, max_tickers=max_tickers, qualified_tickers=qualified_tickers)


def _examples(rows, predicate, limit=3):
    found = [row for row in rows if predicate(row)]
    return {"count": len(found), "examples": [
        {"ticker": row["ticker"], "primary_lane": row.get("primary_lane"),
         "research_priority_tier": row.get("research_priority_tier"),
         "research_action_posture": row.get("research_action_posture"),
         "evolution": row.get("evolution"), "tactical_phase": row.get("tactical_phase"),
         "fundamental_state": row.get("fundamental_state"), "valuation_status": row.get("valuation_status"),
         "deep_dossier": row.get("deep_dossier"), "blocker": row.get("blocker")}
        for row in found[:limit]]}


def _evaluation(report):
    rows = report["overview"]
    dossiers = {item["ticker"]: item for item in report["dossiers"]}
    constructive = {"BREAKOUT_SETUP", "BREAKOUT_CONFIRMED", "EARLY_REVERSAL", "BASE_BUILDING", "BASE"}
    cases = {
        "early_reversal": _examples(rows, lambda row: row.get("primary_lane") == "EARLY_REVERSAL"),
        "forming_base": _examples(rows, lambda row: row.get("primary_lane") == "BASE_ACCUMULATION" or row.get("tactical_phase") in {"BASE_BUILDING", "BASE"}),
        "breakout_candidate": _examples(rows, lambda row: row.get("primary_lane") == "BREAKOUT" and row.get("tactical_phase") != "BREAKOUT_CONFIRMED"),
        "improving_setup": _examples(rows, lambda row: row.get("evolution") == "IMPROVING_CANDIDATE"),
        "failed_or_weakening": _examples(rows, lambda row: row.get("evolution") == "INVALIDATED_OR_WEAKENING"),
        "priority_now_not_action_ready": _examples(rows, lambda row: row.get("research_priority_tier") == "PRIORITY_NOW" and row.get("research_action_posture") in {"WAIT_FOR_CONFIRMATION", "EARLY_WATCH"}),
        "tactical_constructive_fundamental_insufficient": _examples(rows, lambda row: row.get("tactical_phase") in constructive and row.get("fundamental_state") in {None, "INSUFFICIENT"}),
        "valuation_available": _examples(rows, lambda row: row.get("valuation_status") == "AVAILABLE"),
        "valuation_not_available": _examples(rows, lambda row: row.get("valuation_status") != "AVAILABLE"),
    }
    rendered = []
    for ticker, dossier in dossiers.items():
        kinds = [item.get("kind") for item in dossier.get("relationships") or []]
        rendered.append({
            "ticker": ticker, "primary_lane": dossier.get("primary_lane"),
            "evolution": (dossier.get("evolution") or {}).get("code"),
            "posture": (dossier.get("summary") or {}).get("research_action_posture"),
            "transition": (dossier.get("setup_transition") or {}).get("governed_transition_label"),
            "relationship_kinds": kinds,
            "why_inspect": (dossier.get("summary") or {}).get("why_inspect"),
            "questions": [item.get("source_code") for item in (dossier.get("research_questions") or [])[:4]],
        })
    return {
        "status": report["status"], "session": report["session"],
        "previous_qualified_session": report["previous_qualified_session"],
        "selection_authority": report["selection_authority"],
        "selection_blocker": report["selection_blocker"],
        "population": report["population"],
        "qualified_count_lane_sum": report["qualified_count"],
        "unique_qualified_ticker_count": report.get("unique_qualified_ticker_count"),
        "selected_count": report["selected_count"],
        "lane_reports": report["lane_reports"],
        "overlap_count": len(report["overlaps"]),
        "cap_excluded_count": len(report["cap_excluded"]),
        "identity_mismatch_count": len(report["identity_mismatches"]),
        "identity_mismatch_statuses": sorted({item["status"] for item in report["identity_mismatches"]}),
        "statistics": report["statistics"],
        "priority_lineage": report.get("priority_lineage"),
        "verification_passes": report["verification_passes"],
        "cases": cases,
        "rendered_dossiers": rendered,
        "coverage_is_not_attractiveness": True,
        "comparison_to_explicit_preview": {
            "before": "The released preview renders only tickers a person already named. It does not discover a lane, preserve queue order, or join the queue record identity.",
            "after": "This projection selects from the retained daily opportunity queue, keeps each lane's source order, binds the queue record to the integrated decision, and writes support, contradiction, uncertainty, confirmation and research questions without a vote.",
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--current-operation", type=Path, required=True)
    parser.add_argument("--previous-operation", type=Path)
    parser.add_argument("--lanes", nargs="+", default=list(focus.DEFAULT_LANES))
    parser.add_argument("--tiers", nargs="+", default=list(focus.DEFAULT_TIERS))
    parser.add_argument("--max-tickers", type=int, default=8)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    protected = [args.evidence_root, Path(__file__).resolve().parents[1]]
    if os.environ.get("STOCK_LOOKUP_RUNTIME_ROOT"):
        protected.append(Path(os.environ["STOCK_LOOKUP_RUNTIME_ROOT"]))
    if output.exists() or any(output.is_relative_to(root.resolve()) for root in protected):
        parser.error("output must be a NEW directory outside source and retained evidence roots")
    import psutil
    process = psutil.Process()
    before = process.memory_info()._asdict()
    io_before = process.io_counters()._asdict()
    started = time.monotonic()
    try:
        gate = bounded.resource_gate()
        report = evaluate_research_focus(
            repo_root=args.evidence_root, session=args.session,
            current_operation=args.current_operation, previous_operation=args.previous_operation,
            lanes=tuple(args.lanes), tiers=tuple(args.tiers), max_tickers=args.max_tickers)
        rendered = focus.render_markdown(report)
    except (focus.ResearchFocusError, ValueError, OSError) as exc:
        print(json.dumps({"status": "REAL_SESSION_REPLAY_BLOCKED", "reason": str(exc),
                          "elapsed_seconds": time.monotonic() - started}, ensure_ascii=False))
        return 2
    after = process.memory_info()._asdict()
    io_after = process.io_counters()._asdict()
    peak = after.get("peak_wset", after["rss"])
    private_peak = after.get("peak_pagefile")
    measurements = {
        "status": "MEASURED",
        "report_status": report["status"],
        "artifact_identity": report["artifact_identity"],
        "elapsed_seconds": time.monotonic() - started,
        "memory_before": before, "memory_after": after,
        "peak_process_resident_bytes": peak,
        "peak_incremental_resident_bytes": max(0, peak - before["rss"]),
        "peak_incremental_private_bytes": None if private_peak is None else max(0, private_peak - before.get("private", before.get("pagefile", 0))),
        "measurement_method": "Windows OS process high-water counters; RSS and private commit reported independently",
        "resource_gate": gate,
        "io_counter_delta": {key: value - io_before[key] for key, value in io_after.items()},
        "verification_passes": report["verification_passes"],
        "selected_count": report["selected_count"],
        "unique_qualified_ticker_count": report.get("unique_qualified_ticker_count"),
    }
    if measurements["peak_incremental_resident_bytes"] >= 1024**3 or (
            measurements["peak_incremental_private_bytes"] or 0) >= 1024**3:
        print(json.dumps({**measurements, "status": "REAL_SESSION_REPLAY_BLOCKED", "reason": "MEASURED_MEMORY_TARGET_EXCEEDED"}))
        return 2
    output.mkdir(parents=True, exist_ok=False)
    report_text = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    markdown = rendered
    (output / "research_focus.json").write_text(report_text, encoding="utf-8")
    (output / "research_focus.md").write_text(markdown, encoding="utf-8")
    measurements["rendered_json_bytes"] = len(report_text.encode("utf-8"))
    measurements["rendered_markdown_bytes"] = len(markdown.encode("utf-8"))
    (output / "measurements.json").write_text(json.dumps(measurements, indent=2) + "\n", encoding="utf-8")
    (output / "evaluation_summary.json").write_text(
        json.dumps(_evaluation(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(measurements, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
