"""Opt-in research-focus projection. No posture, score, valuation, or execution authority.

Lane order and tiers stay on the daily opportunity queue. Canonical posture, coherence,
confirmation and invalidation stay on their source records. This module verifies those
records and explains the relationship a reader can already inspect.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

import daily_opportunity_decision_queue as decision_queue
import daily_research_session_operations as operations
import next_session_decision_brief as next_session
import personal_investment_decision_action_center as action_center
import stocklookup_core.financial.fundamental_signal_consumption_contract as fundamental_signals
from stocklookup_core.decision import bounded_research_preview as bounded
from stocklookup_core.decision import current_opportunity_prioritization as opportunity
from stocklookup_core.decision import integrated_investment_decision_product as integrated
from stocklookup_core.evidence.bounded_json import canonical_bytes
from stocklookup_core.evidence.field_identity import stable_id

CONTRACT = "current_research_priority_focus/v1"
QUEUE_FILE = "daily_opportunity_decision_queue_artifact.json"
OPPORTUNITY_FILE = "opportunity_prioritization_artifact.json"
SOURCE_JSON_LIMIT = 16 * 1024 * 1024
DEFAULT_LANES = ("EARLY_REVERSAL", "BASE_ACCUMULATION", "BREAKOUT")
DEFAULT_TIERS = ("PRIORITY_NOW", "SETUP_WATCH")
LANE_OBJECTIVE = {
    "EARLY_REVERSAL": "Nghiên cứu cấu trúc đảo chiều sớm. Mức chú ý không có nghĩa là đảo chiều đã được xác nhận.",
    "BASE_ACCUMULATION": "Nghiên cứu nền giá đang hình thành. Cấu trúc nền không phải bằng chứng dòng tiền tổ chức.",
    "BREAKOUT": "Nghiên cứu cấu trúc phá nền. Trạng thái chờ xác nhận khác với phá nền nguồn đã xác nhận.",
    "TREND_MOMENTUM": "Nghiên cứu xu hướng hoặc động lượng theo đúng làn nguồn đã phân loại.",
    "FUNDAMENTAL_IMPROVEMENT": "Nghiên cứu cải thiện cơ bản theo nguồn. Một kỳ lợi nhuận ngắn không thành luận điểm cấu trúc.",
    "EVENT_DRIVEN": "Nghiên cứu sự kiện đã đủ điều kiện. Không suy ra ngày hiệu lực hay ngày giao dịch không hưởng quyền.",
    "VALUE": "Làn giá trị của nguồn. Hợp đồng hàng đợi không cho dùng định giá bóng thay cho giá trị bị chặn.",
}
CONSTRUCTIVE_FUNDAMENTAL = frozenset({
    integrated.FUNDAMENTAL_IMPROVING, integrated.FUNDAMENTAL_STABLE, integrated.FUNDAMENTAL_TURNAROUND,
})
QUESTION_BY_CODE = {
    "FUNDAMENTAL_CONTEXT_ABSENT": "Liệu có một sự thật tài chính chính thức cho kỳ so sánh được hay không?",
    "FUNDAMENTAL_STALE_EVIDENCE_ONLY_NO_CURRENT_DIRECTION": "Liệu xu hướng cơ bản có được một kỳ tài chính còn hiệu lực và cùng loại hỗ trợ hay không?",
    "FUNDAMENTAL_CURRENT_DIRECTION_INSUFFICIENT": "Liệu bằng chứng hiện có chỉ đủ mô tả, chưa đủ kết luận hướng cơ bản hay không?",
    "VALUATION_NO_USABLE_RELATIVE_METHOD": "Liệu định giá đang bị chặn bởi cơ sở cổ phiếu, đơn vị, kỳ hoặc phương pháp không so được hay không?",
    "VALUATION_CONTEXT_NOT_PROVIDED": "Liệu nguồn định giá của phiên này có mặt hay không?",
    "PRICE_BASIS_UNVERIFIED": "Liệu mức kích hoạt có đánh giá được khi nền giá chưa được xác minh hay không?",
    "CONDITION_NOT_MACHINE_EVALUABLE": "Điều kiện nào vẫn nằm ở tương lai và chưa phải sự kiện đã quan sát?",
    "CURRENT_PRICE_NOT_ESTABLISHED": "Liệu giá hiện hành dùng cho mức kích hoạt đã được thiết lập hay chưa?",
    "SECTOR_LEADERSHIP_UNKNOWN_OR_DATA_LIMITED": "Bối cảnh ngành đang thiếu, chứ không phải trung tính?",
    "CORPORATE_INTELLIGENCE_EVIDENCE_SESSION_STALE": "Sự kiện doanh nghiệp thuộc phiên nào, và có còn được gọi là hiện hành hay không?",
}


class ResearchFocusError(ValueError):
    pass


def content_identity(body: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: value for key, value in body.items() if key not in {"artifact_sha256", "artifact_identity"}}
    digest = hashlib.sha256(canonical_bytes(payload)).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"{CONTRACT}:{digest}"}


def _load_bounded_json(path: Path) -> dict[str, Any]:
    if path.stat().st_size > SOURCE_JSON_LIMIT:
        raise ResearchFocusError("SOURCE_JSON_LIMIT:" + path.name)
    with path.open(encoding="utf-8") as source:
        text = source.read(SOURCE_JSON_LIMIT + 1)
    if len(text) > SOURCE_JSON_LIMIT:
        raise ResearchFocusError("SOURCE_JSON_LIMIT:" + path.name)
    return json.loads(text, object_pairs_hook=bounded.strict_object, parse_constant=bounded.reject_constant,
                      parse_float=bounded.finite_float)


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


def select_from_queue(queue: Mapping[str, Any], *, lanes: Sequence[str], tiers: Sequence[str],
                      max_tickers: int, include_tickers: Sequence[str] | None = None) -> dict[str, Any]:
    """Preserve each lane's source order. Do not invent a score across lanes."""
    if isinstance(lanes, str) or isinstance(tiers, str) or isinstance(include_tickers, str):
        raise ResearchFocusError("SELECTION_SEQUENCES_REQUIRED")
    requested = list(lanes)
    if not requested or len(set(requested)) != len(requested):
        raise ResearchFocusError("SELECTION_LANES_INVALID")
    unknown = [lane for lane in requested if lane not in decision_queue.LANES]
    if unknown:
        raise ResearchFocusError("QUEUE_LANE_NOT_IN_SOURCE_CONTRACT:" + ",".join(unknown))
    allowed = list(tiers)
    if not allowed or len(set(allowed)) != len(allowed) or any(tier not in opportunity.TIERS for tier in allowed):
        raise ResearchFocusError("SELECTION_TIERS_INVALID")
    if not isinstance(max_tickers, int) or isinstance(max_tickers, bool) or not 1 <= max_tickers <= bounded.MAX_SELECTED:
        raise ResearchFocusError("SELECTION_LIMIT_OR_INVALID_TICKER")
    include = None
    if include_tickers is not None:
        include = list(include_tickers)
        if not include or len(set(include)) != len(include):
            raise ResearchFocusError("SELECTION_LIMIT_OR_INVALID_TICKER")
    records = queue["records"]
    selected: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}
    overlaps = []
    cap_excluded = []
    missing_includes = []
    qualified_by_lane = []
    lane_reports = []
    for lane in requested:
        qualified = [row for row in queue["lane_queues"][lane]["tickers"]
                     if row["lane_priority"] in allowed and (include is None or row["ticker"] in include)]
        qualified_by_lane.append(qualified)
        counts = Counter(row["lane_priority"] for row in qualified)
        lane_reports.append({
            "lane": lane, "objective": LANE_OBJECTIVE[lane],
            "source_count": queue["lane_queues"][lane]["count"],
            "source_tier_counts": queue["lane_queues"][lane]["tier_counts"],
            "qualified_count": len(qualified),
            "qualified_tier_counts": {tier: counts.get(tier, 0) for tier in allowed},
            "selected_tickers": [],
            "ordering": "SOURCE_LANE_ORDER_PRESERVED_CAP_IS_ROUND_ROBIN_NOT_A_SCORE",
        })
    unique_qualified = {row["ticker"] for rows in qualified_by_lane for row in rows}
    cursors = [0 for _ in requested]
    while len(selected) < max_tickers:
        progressed = False
        for index, lane in enumerate(requested):
            rows = qualified_by_lane[index]
            while cursors[index] < len(rows) and rows[cursors[index]]["ticker"] in seen:
                row = rows[cursors[index]]
                seen[row["ticker"]]["lanes"].append(lane)
                overlaps.append({"ticker": row["ticker"], "lane": lane,
                                 "reason": "ALREADY_SELECTED_IN_EARLIER_REQUESTED_LANE"})
                cursors[index] += 1
            if cursors[index] >= len(rows) or len(selected) >= max_tickers:
                continue
            row = rows[cursors[index]]
            cursors[index] += 1
            item = {"ticker": row["ticker"], "primary_lane": lane, "lanes": [lane],
                    "lane_priority": row["lane_priority"], "source_index": len(lane_reports[index]["selected_tickers"])}
            selected.append(item)
            seen[row["ticker"]] = item
            lane_reports[index]["selected_tickers"].append(row["ticker"])
            progressed = True
        if not progressed:
            break
    for index, lane in enumerate(requested):
        for row in qualified_by_lane[index][cursors[index]:]:
            if row["ticker"] in seen:
                continue
            cap_excluded.append({"ticker": row["ticker"], "lane": lane, "lane_priority": row["lane_priority"],
                                 "reason": "BOUNDED_SELECTION_CAP"})
    if include is not None:
        qualified_names = {item["ticker"] for item in selected} | {item["ticker"] for item in cap_excluded} | {
            item["ticker"] for item in overlaps}
        missing_includes = [{"ticker": ticker, "reason": "NOT_IN_QUALIFIED_LANE_SOURCE"}
                            for ticker in include if ticker not in qualified_names and ticker not in records]
        missing_includes += [{"ticker": ticker, "reason": "NOT_IN_REQUESTED_LANE_AND_TIER"}
                             for ticker in include if ticker in records and ticker not in qualified_names]
    return {
        "lanes": lane_reports,
        "selected": selected,
        "overlaps": overlaps,
        "cap_excluded": cap_excluded,
        "inclusion_exclusions": missing_includes,
        "queue_denominator": len(records),
        "qualified_count": sum(lane["qualified_count"] for lane in lane_reports),
        "unique_qualified_ticker_count": len(unique_qualified),
        "selected_count": len(selected),
    }


def _priority_lineage(queue: Mapping[str, Any] | None, metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """The decision records which queue artifact it consumed. The operation output may be a later seal."""
    decision_queue = ((metadata or {}).get("source_artifacts") or {}).get("priority_queue")
    operation_queue = None if queue is None else queue.get("artifact_identity")
    same = isinstance(decision_queue, str) and decision_queue == operation_queue
    if isinstance(decision_queue, str) and isinstance(operation_queue, str) and not same:
        status = "INTEGRATED_DECISION_BUILT_FROM_A_DIFFERENT_PRIORITY_QUEUE"
    elif same:
        status = "SAME_QUEUE_ARTIFACT"
    else:
        status = "DECISION_PRIORITY_QUEUE_IDENTITY_ABSENT"
    return {
        "status": status,
        "operation_queue_identity": operation_queue,
        "integrated_decision_priority_queue_identity": decision_queue if isinstance(decision_queue, str) else None,
        "record_identity_comparable": same,
    }


def _bind(queue_record: Mapping[str, Any], decision: Mapping[str, Any] | None, opportunity_record: Mapping[str, Any],
          *, require_queue_record_identity: bool = True) -> dict[str, Any]:
    if decision is None:
        return {"status": "INTEGRATED_DECISION_RECORD_ABSENT", "reason": "TICKER_NOT_IN_INTEGRATED_DECISION_POPULATION"}
    priority_identity = (decision.get("source_identities") or {}).get("priority_queue_record_identity")
    reasons = []
    if require_queue_record_identity and priority_identity != queue_record.get("content_identity"):
        reasons.append("PRIORITY_QUEUE_RECORD_IDENTITY_MISMATCH")
    if opportunity_record.get("content_identity") != queue_record.get("opportunity_record_content_identity"):
        reasons.append("OPPORTUNITY_RECORD_IDENTITY_MISMATCH")
    view = decision.get("opportunity_priority") or {}
    if view.get("status") != "AVAILABLE" or view.get("research_priority_tier") != queue_record.get("research_priority_tier"):
        reasons.append("EMBEDDED_PRIORITY_TIER_MISMATCH")
    if view.get("entry_relevant") != queue_record.get("entry_relevant"):
        reasons.append("EMBEDDED_ENTRY_RELEVANCE_MISMATCH")
    if decision.get("ticker") != queue_record.get("ticker"):
        reasons.append("TICKER_MISMATCH")
    if reasons:
        return {"status": "SOURCE_IDENTITY_MISMATCH", "reason_codes": reasons}
    return {"status": "BOUND", "priority_queue_record_identity": priority_identity,
            "opportunity_record_content_identity": queue_record.get("opportunity_record_content_identity")}


def _slim(row: Mapping[str, Any]) -> dict[str, Any]:
    valuation = row.get("valuation_context_summary") or {}
    market = row.get("market_sector_context") or {}
    coherence = row.get("evidence_axis_coherence") or {}
    return {
        "ticker": row.get("ticker"),
        "as_of_session": row.get("as_of_session"),
        "decision_identity": row.get("decision_identity"),
        "research_action_posture": row.get("research_action_posture"),
        "posture_condition_class": row.get("posture_condition_class"),
        "research_action_policy_version": row.get("research_action_policy_version", "v1"),
        "fundamental_decision_policy_version": row.get("fundamental_decision_policy_version"),
        "tactical_phase": row.get("tactical_phase"),
        "breakout_state_v3": row.get("breakout_state_v3"),
        "fundamental_state": row.get("fundamental_state"),
        "fundamental_evidence_availability": row.get("fundamental_evidence_availability"),
        "evidence_currency": row.get("evidence_currency"),
        "priority_queue_record_identity": (row.get("source_identities") or {}).get("priority_queue_record_identity"),
        "opportunity_priority": {
            "status": (row.get("opportunity_priority") or {}).get("status"),
            "research_priority_tier": (row.get("opportunity_priority") or {}).get("research_priority_tier"),
            "entry_relevant": (row.get("opportunity_priority") or {}).get("entry_relevant"),
        },
        "source_identities": {"priority_queue_record_identity": (row.get("source_identities") or {}).get("priority_queue_record_identity")},
        "coherence_state": coherence.get("state"),
        "coherence_reason_codes": list(coherence.get("reason_codes") or []),
        "valuation_status": valuation.get("status"),
        "peer_relative_state": valuation.get("peer_relative_state"),
        "valuation_claim": (valuation.get("pb_basis") or {}).get("claim") if isinstance(valuation.get("pb_basis"), Mapping) else None,
        "market_regime": market.get("market_regime"),
        "sector_leadership": market.get("sector_leadership"),
    }


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
        import time
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
            slim[ticker] = _slim(row)
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
            queue = _verified_queue(native / QUEUE_FILE, session=session, expected_identity=queue_identity)
            opportunity_artifact = _verified_opportunity(native / OPPORTUNITY_FILE, session=session, expected_identity=opportunity_identity)
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
                     queue_bytes=0 if queue is None else (native / QUEUE_FILE).stat().st_size,
                     opportunity_bytes=0 if opportunity_artifact is None else (native / OPPORTUNITY_FILE).stat().st_size)
    return projected


def _evolution(previous: Mapping[str, Any] | None, current: Mapping[str, Any], transition: str,
               confirmation: str) -> dict[str, Any]:
    """Investor description of existing labels. Not a trading-policy state."""
    basis = ["governed_transition_label:" + transition]
    if transition == "NOT_COMPARABLE_POLICY_CHANGE" or (
            previous is not None and not fundamental_signals.epochs_comparable(previous, current)
            and previous.get("fundamental_state") != current.get("fundamental_state")):
        return {"code": "NOT_COMPARABLE", "basis": basis + ["POLICY_OR_FUNDAMENTAL_EPOCH"], "causal": False}
    if previous is None or transition in {"NEWLY_AVAILABLE", "NEW_BREAKOUT", "NEW_EARLY_WATCH", "NEW_RETEST_CANDIDATE"}:
        return {"code": "NEW_CANDIDATE", "basis": basis, "causal": False}
    if transition in {"BREAKOUT_FAILED", "UPTREND_TO_BREAKDOWN"} or current.get("tactical_phase") == integrated.TACTICAL_BREAKDOWN:
        return {"code": "INVALIDATED_OR_WEAKENING", "basis": basis + ["tactical_phase:" + str(current.get("tactical_phase"))], "causal": False}
    action_ready = current.get("research_action_posture") in {"INITIATE_ON_BREAKOUT", "HOLD", "ACCUMULATE_ON_RETEST"}
    if current.get("tactical_phase") == integrated.TACTICAL_BREAKOUT_CONFIRMED or (
            action_ready and confirmation in {"GAINED_CONFIRMATION", "RETAINED_CONFIRMATION"}):
        return {"code": "CONFIRMED_SETUP", "basis": basis + ["confirmation:" + confirmation,
               "tactical_phase:" + str(current.get("tactical_phase"))], "causal": False}
    if previous is not None and fundamental_signals.epochs_comparable(previous, current):
        before, after = previous.get("fundamental_state"), current.get("fundamental_state")
        if before == integrated.FUNDAMENTAL_DETERIORATING and after in CONSTRUCTIVE_FUNDAMENTAL:
            return {"code": "IMPROVING_CANDIDATE", "basis": basis + ["fundamental_state"], "causal": False}
        if before in CONSTRUCTIVE_FUNDAMENTAL and after == integrated.FUNDAMENTAL_DETERIORATING:
            return {"code": "INVALIDATED_OR_WEAKENING", "basis": basis + ["fundamental_state"], "causal": False}
    if (current.get("research_action_posture") in {"WAIT_FOR_CONFIRMATION", "EARLY_WATCH"}
            or current.get("tactical_phase") == integrated.TACTICAL_BREAKOUT_SETUP
            or current.get("breakout_state_v3") in {"TESTING_PIVOT", "NO_VALID_PIVOT"}):
        return {"code": "AWAITING_CONFIRMATION", "basis": basis, "causal": False}
    return {"code": "SOURCE_LABEL_ONLY", "basis": basis, "causal": False}


def _relationships(queue_record: Mapping[str, Any], decision: Mapping[str, Any]) -> list[dict[str, Any]]:
    coherence = decision.get("evidence_axis_coherence") or {}
    phase = decision.get("tactical_phase")
    fund = decision.get("fundamental_state")
    posture = decision.get("research_action_posture")
    tier = queue_record.get("research_priority_tier")
    market = (decision.get("market_sector_context") or {}).get("market_regime")
    valuation = decision.get("valuation_context_summary") or {}
    items = [{
        "kind": "SOURCE_COHERENCE", "state": coherence.get("state"),
        "reason_codes": list(coherence.get("reason_codes") or []), "causal": False,
    }]
    if tier == "PRIORITY_NOW" and posture in {"WAIT_FOR_CONFIRMATION", "EARLY_WATCH"}:
        items.append({"kind": "PRIORITY_DIFFERS_FROM_ACTION_READINESS", "research_priority_tier": tier,
                      "research_action_posture": posture, "causal": False})
    if phase in integrated._CONSTRUCTIVE_TACTICAL_PHASES and fund == integrated.FUNDAMENTAL_INSUFFICIENT:
        items.append({"kind": "TACTICAL_CONSTRUCTIVE_FUNDAMENTAL_INSUFFICIENT", "tactical_phase": phase,
                      "fundamental_state": fund, "missing_is_not_negative_evidence": True, "causal": False})
    constructive_lanes = [lane for lane in ("EARLY_REVERSAL", "BASE_ACCUMULATION", "BREAKOUT")
                          if lane in (queue_record.get("lane_specific_priority") or {})]
    if constructive_lanes and phase == integrated.TACTICAL_BREAKDOWN:
        items.append({"kind": "QUEUE_LANE_REMAINS_WHILE_TACTICAL_PHASE_IS_BREAKDOWN",
                      "lanes": constructive_lanes, "tactical_phase": phase, "causal": False})
    if phase in integrated._CONSTRUCTIVE_TACTICAL_PHASES and fund == integrated.FUNDAMENTAL_DETERIORATING:
        items.append({"kind": "STRUCTURAL_CONCERN_WITH_TACTICAL_RECOVERY", "tactical_phase": phase,
                      "fundamental_state": fund, "causal": False})
    if phase in integrated._CONSTRUCTIVE_TACTICAL_PHASES and market in integrated._ADVERSE_MARKET_REGIMES:
        items.append({"kind": "TACTICAL_CONSTRUCTIVE_MARKET_CONTEXT_WEAK", "market_regime": market,
                      "market_weakness_is_context_not_a_veto": True, "causal": False})
    claim = (valuation.get("pb_basis") or {}).get("claim") if isinstance(valuation.get("pb_basis"), Mapping) else None
    if valuation.get("status") == "AVAILABLE" and claim == "RESEARCH_ONLY_NOT_EXACT_NOT_COMMON_SHAREHOLDER":
        items.append({"kind": "VALUATION_RESEARCH_PROXY", "claim": claim, "causal": False})
    elif valuation.get("status") != "AVAILABLE":
        items.append({"kind": "VALUATION_NOT_USABLE", "status": valuation.get("status"),
                      "reason_codes": list(valuation.get("unavailable_reason_codes") or []),
                      "missing_is_not_negative_evidence": True, "causal": False})
    if valuation.get("peer_relative_state") in {"NOT_APPLICABLE", "NOT_COMPARABLE"}:
        items.append({"kind": "NON_COMPARABLE", "field": "peer_relative_state",
                      "state": valuation.get("peer_relative_state"), "causal": False})
    exact = list(decision.get("exact_capabilities_unavailable") or [])
    if exact:
        items.append({"kind": "HISTORICAL_OR_EXACT_AUTHORITY_CLOSED", "exact_capabilities_unavailable": exact, "causal": False})
    return items


def _questions(queue_record: Mapping[str, Any], decision: Mapping[str, Any], details: Mapping[str, Any]) -> list[dict[str, str]]:
    codes = []
    codes.extend(queue_record.get("blocking_reasons") or [])
    codes.extend((decision.get("missing_evidence_decision_effect") or {}).get("reason_codes") or []
                 if isinstance(decision.get("missing_evidence_decision_effect"), Mapping) else [])
    synthesis = decision.get("fundamental_synthesis") or {}
    codes.extend(synthesis.get("blocker_reason_codes") or [])
    valuation = decision.get("valuation_context_summary") or {}
    codes.extend(valuation.get("unavailable_reason_codes") or [])
    for role in ("trigger", "invalidation"):
        codes.extend((details.get(role) or {}).get("numeric_display_reason_codes") or [])
    corporate = decision.get("corporate_intelligence_context") or {}
    codes.extend(corporate.get("blocker_reason_codes") or [])
    questions = []
    seen = set()
    for code in codes:
        text = str(code)
        if not text or text in seen:
            continue
        seen.add(text)
        questions.append({"source_code": text, "question": QUESTION_BY_CODE.get(
            text, "Mã nguồn " + text + " còn mở. Cần đọc đúng hợp đồng nguồn trước khi kết luận.")})
    event = corporate.get("freshest_material_event")
    if isinstance(event, Mapping) and event.get("effective_date") in (None, ""):
        questions.append({"source_code": "EFFECTIVE_DATE_ABSENT",
                          "question": "Sự kiện doanh nghiệp có ngày hiệu lực chính thức hay không? Không suy ra ngày này."})
    if not questions:
        questions.append({"source_code": "NO_OPEN_BLOCKER_CODE",
                          "question": "Nguồn không để một mã chặn mở. Việc không có mã chặn không phải khuyến nghị mua."})
    return questions


def _corporate(decision: Mapping[str, Any]) -> dict[str, Any]:
    context = decision.get("corporate_intelligence_context") or {}
    event = context.get("freshest_material_event")
    timing = None
    if isinstance(event, Mapping):
        kept = {key: event.get(key) for key in (
            "event_id", "identity", "event_identity", "title", "event_type", "materiality", "direction",
            "status", "lifecycle", "knowledge_time", "published_at", "disclosure_time", "effective_date",
            "ex_date", "source", "source_identity", "limitations") if key in event}
        timing = {"effective_date": kept.get("effective_date"), "ex_date": kept.get("ex_date"),
                  "effective_date_status": "PRESENT" if kept.get("effective_date") else "NOT_PRESENT_NOT_INFERRED",
                  "ex_date_status": "PRESENT" if kept.get("ex_date") else "NOT_PRESENT_NOT_INFERRED",
                  "lifecycle": kept.get("lifecycle") or kept.get("status"), "ex_date_inferred": False}
        event = kept
    return {
        "state": context.get("state"), "fitness": context.get("fitness"),
        "evidence_session": context.get("evidence_session"),
        "evidence_session_stale": context.get("evidence_session_stale"),
        "active_catalyst_count": context.get("active_catalyst_count"),
        "active_risk_count": context.get("active_risk_count"),
        "supporting_reason_codes": list(context.get("supporting_reason_codes") or []),
        "contradicting_reason_codes": list(context.get("contradicting_reason_codes") or []),
        "freshest_material_event": event, "timing": timing,
        "authority": "SOURCE_EVENT_FIELDS_ONLY_NO_EX_DATE_INFERENCE",
    }


def _valuation(decision: Mapping[str, Any]) -> dict[str, Any]:
    summary = copy.deepcopy(decision.get("valuation_context_summary") or {})
    summary.pop("peer_percentile", None)
    size = summary.get("size_context") or {}
    return {
        "status": summary.get("status"),
        "peer_relative_state": summary.get("peer_relative_state"),
        "peer_relative_basis": summary.get("peer_relative_basis"),
        "own_history_state": summary.get("own_history_state"),
        "share_basis": summary.get("share_basis"),
        "earnings_state": summary.get("earnings_state"),
        "multiples": {key: summary.get(key) for key in ("pe_multiple", "pb_multiple", "ps_multiple", "ev_ebitda_multiple")},
        "pb_basis": summary.get("pb_basis"),
        "size_context": size,
        "unavailable_reason_codes": list(summary.get("unavailable_reason_codes") or []),
        "limitations": list(summary.get("limitations") or []),
        "method_reconciliation": summary.get("valuation_method_reconciliation") or {},
        "prohibited": "NO_FAIR_VALUE_MARGIN_OF_SAFETY_UPSIDE_TARGET_OR_EXPECTED_RETURN",
        "market_cap_is_size_context_not_valuation": size.get("role") == "SIZE_CONTEXT_NOT_A_VALUATION_MULTIPLE" or True,
    }


def _confirmation(decision: Mapping[str, Any], details: Mapping[str, Any], tactical_state: str | None) -> dict[str, Any]:
    trigger = details.get("trigger") or {}
    invalidation = details.get("invalidation") or {}
    observed = trigger.get("status") == "TRIGGERED" or decision.get("tactical_phase") == integrated.TACTICAL_BREAKOUT_CONFIRMED
    return {
        "observed_confirmation": observed,
        "tactical_entry_state": tactical_state,
        "tactical_phase": decision.get("tactical_phase"),
        "breakout_state_v3": decision.get("breakout_state_v3"),
        "trigger_status": trigger.get("status") or (decision.get("trigger") or {}).get("status"),
        "future_trigger_is_not_an_observed_event": trigger.get("status") != "TRIGGERED",
        "trigger": trigger, "invalidation": invalidation,
        "numeric_levels_withheld": trigger.get("numeric_display_status") != "AVAILABLE"
        or invalidation.get("numeric_display_status") != "AVAILABLE",
    }


def _dossier(item: Mapping[str, Any], queue_record: Mapping[str, Any], decision: Mapping[str, Any],
             previous: Mapping[str, Any] | None, *, session: str, previous_session: str | None,
             transition_label: str, confirmation_status: str, brief: Mapping[str, Any],
             current_view: Mapping[str, Any], previous_view: Mapping[str, Any] | None) -> dict[str, Any]:
    lineage = decision.get("evidence_currency_lineage") or {}
    coverage = {item["ticker"]: lineage} if lineage.get("method") == integrated.EVIDENCE_CURRENCY_SOURCE_CONTRACT else {}
    evidence = action_center._evidence_block(item["ticker"], decision, session=session, coverage_records=coverage)
    details = action_center._conditional_research_details(decision, evidence)
    for role in ("trigger", "invalidation"):
        boundary = details[role]
        if not (boundary.get("price_basis") or {}).get("price_unit"):
            boundary["numeric_display_status"] = "WITHHELD_UNQUALIFIED_BOUNDARY"
            boundary["numeric_display_reason_codes"].append("PRICE_UNIT_NOT_QUALIFIED")
            boundary[role + "_level"] = boundary["distance_to_" + role + "_pct"] = None
    transition = action_center._setup_transition_for_ticker(
        session=session, ticker=item["ticker"], current_artifact=current_view, previous_artifact=previous_view, brief=brief)
    if previous is not None and not fundamental_signals.epochs_comparable(previous, decision):
        transition["research_limitations"].append("FUNDAMENTAL_POLICY_EPOCH_CHANGE_NO_FUNDAMENTAL_EVOLUTION_INFERENCE")
    evolution = _evolution(previous, decision, transition_label, confirmation_status)
    lane = item.get("primary_lane")
    support = list(decision.get("technical_support") or []) + list(decision.get("fundamental_support") or [])
    support += list(queue_record.get("priority_reasons") or [])
    oppose = list(decision.get("counter_thesis") or []) + list(queue_record.get("blocking_reasons") or [])
    synthesis = decision.get("fundamental_synthesis") or {}
    oppose += list(synthesis.get("contradicting_reason_codes") or [])
    return {
        "ticker": item["ticker"],
        "primary_lane": item["primary_lane"],
        "lanes": list(item["lanes"]),
        "multi_lane": len(item["lanes"]) > 1,
        "summary": {
            "why_inspect": (decision.get("why_now") or [None])[0] if isinstance(decision.get("why_now"), list) else decision.get("why_now"),
            "lane_objective": LANE_OBJECTIVE.get(lane, "Lựa chọn làn nguồn bị chặn. Đây là xem trước mã chỉ định, không phải phát hiện làn."),
            "research_priority_tier": queue_record.get("research_priority_tier"),
            "lane_priority": None if lane not in LANE_OBJECTIVE else (queue_record.get("lane_specific_priority") or {}).get(lane),
            "entry_relevant": queue_record.get("entry_relevant"),
            "research_action_posture": decision.get("research_action_posture"),
            "attention_is_not_action_readiness": True,
            "evolution": evolution["code"],
            "coherence_state": (decision.get("evidence_axis_coherence") or {}).get("state"),
        },
        "discovery": {
            "priority_reasons": list(queue_record.get("priority_reasons") or []),
            "blocking_reasons": list(queue_record.get("blocking_reasons") or []),
            "warnings": list(queue_record.get("invalidation_or_context_warnings") or []),
            "tactical_state": queue_record.get("tactical_state"),
            "entry_action": queue_record.get("entry_action"),
            "authority_note": queue_record.get("authority_note"),
        },
        "tactical_market_sector": {
            "tactical_phase": decision.get("tactical_phase"),
            "market_structure_state": decision.get("market_structure_state"),
            "breakout_state_v3": decision.get("breakout_state_v3"),
            "technical_support": list(decision.get("technical_support") or []),
            "market_sector_context": decision.get("market_sector_context"),
            "market_weakness_is_context_not_a_new_veto": True,
            "technical_structure_is_not_institutional_flow": True,
        },
        "fundamental": {
            "fundamental_state": decision.get("fundamental_state"),
            "fundamental_evidence_availability": decision.get("fundamental_evidence_availability"),
            "fundamental_risk_level": decision.get("fundamental_risk_level"),
            "supporting_reason_codes": list(synthesis.get("supporting_reason_codes") or []),
            "contradicting_reason_codes": list(synthesis.get("contradicting_reason_codes") or []),
            "financial_composite_context": decision.get("financial_composite_context"),
            "short_run_change_is_not_a_structural_thesis": True,
        },
        "valuation": _valuation(decision),
        "corporate": _corporate(decision),
        "thesis": {"supporting": support, "opposing": oppose,
                   "uncertain": list(decision.get("material_uncertainties") or []),
                   "not_a_vote": True},
        "counter_thesis": list(decision.get("counter_thesis") or []),
        "evolution": evolution,
        "setup_transition": transition,
        "confirmation": _confirmation(decision, details, None),
        "relationships": _relationships(queue_record, decision),
        "research_questions": _questions(queue_record, decision, details),
        "source": {
            "decision_identity": decision.get("decision_identity"),
            "previous_decision_identity": None if previous is None else previous.get("decision_identity"),
            "previous_session": previous_session,
            "evidence_currency": decision.get("evidence_currency"),
            "research_action_policy_version": decision.get("research_action_policy_version", "v1"),
            "fundamental_decision_policy_version": decision.get("fundamental_decision_policy_version"),
            "priority_queue_record_identity": queue_record.get("content_identity"),
            "decision_priority_queue_record_identity": (decision.get("source_identities") or {}).get("priority_queue_record_identity"),
            "opportunity_record_content_identity": queue_record.get("opportunity_record_content_identity"),
            "queue_record_identity_comparable": queue_record.get("content_identity") == (decision.get("source_identities") or {}).get("priority_queue_record_identity"),
        },
        "authority_boundary": {"is_actionable": False, "authority_effect": "NONE"},
    }


def _overview_row(item: Mapping[str, Any], queue_record: Mapping[str, Any], slim: Mapping[str, Any] | None,
                  evolution: str | None, blocker: str | None, *, deep: bool) -> dict[str, Any]:
    posture = None if slim is None else slim.get("research_action_posture")
    reason = (queue_record.get("priority_reasons") or [None])[0]
    return {
        "ticker": item["ticker"], "primary_lane": item["primary_lane"], "lanes": list(item["lanes"]),
        "multi_lane": len(queue_record.get("lane_specific_priority") or {}) > 1,
        "lane_priority": item["lane_priority"], "research_priority_tier": queue_record.get("research_priority_tier"),
        "research_action_posture": posture, "evolution": evolution,
        "coherence_state": None if slim is None else slim.get("coherence_state"),
        "fundamental_state": None if slim is None else slim.get("fundamental_state"),
        "valuation_status": None if slim is None else slim.get("valuation_status"),
        "tactical_phase": None if slim is None else slim.get("tactical_phase"),
        "one_reason": reason, "blocker": blocker, "deep_dossier": deep,
    }


def _statistics(rows: Sequence[Mapping[str, Any]], dossiers: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def count(predicate) -> int:
        return sum(1 for row in rows if predicate(row))
    transitions = Counter(dossier["setup_transition"].get("governed_transition_label") for dossier in dossiers)
    withheld = Counter()
    for dossier in dossiers:
        confirmation = dossier["confirmation"]
        if confirmation["numeric_levels_withheld"]:
            withheld["WITHHELD_OR_PARTIAL"] += 1
        else:
            withheld["AVAILABLE"] += 1
    return {
        "qualified_rows": len(rows),
        "deep_dossier_count": len(dossiers),
        "current_technical_evidence": count(lambda row: row.get("tactical_phase") not in {None, "INSUFFICIENT_HISTORY"}),
        "fundamental_directional": count(lambda row: row.get("fundamental_state") not in {None, integrated.FUNDAMENTAL_INSUFFICIENT}),
        "fundamental_insufficient_or_absent": count(lambda row: row.get("fundamental_state") in {None, integrated.FUNDAMENTAL_INSUFFICIENT}),
        "fundamental_deteriorating": count(lambda row: row.get("fundamental_state") == integrated.FUNDAMENTAL_DETERIORATING),
        "valuation_available": count(lambda row: row.get("valuation_status") == "AVAILABLE"),
        "valuation_not_available": count(lambda row: row.get("valuation_status") != "AVAILABLE"),
        "contradictory_axes": count(lambda row: row.get("coherence_state") == integrated.EVIDENCE_AXIS_COHERENCE_CONTRADICTED),
        "priority_now_not_action_ready": count(lambda row: row.get("research_priority_tier") == "PRIORITY_NOW" and row.get("research_action_posture") in {"WAIT_FOR_CONFIRMATION", "EARLY_WATCH"}),
        "transition_labels": dict(sorted((key, value) for key, value in transitions.items() if key)),
        "numeric_boundary_rows": dict(sorted(withheld.items())),
        "coverage_is_not_attractiveness": True,
        "missing_fundamental_is_not_a_negative_business_signal": True,
    }


def evaluate_research_focus(*, repo_root: Path, session: str, current_operation: Path,
                            previous_operation: Path | None = None, lanes: Sequence[str] = DEFAULT_LANES,
                            tiers: Sequence[str] = DEFAULT_TIERS, max_tickers: int = 8,
                            include_tickers: Sequence[str] | None = None,
                            explicit_tickers_when_queue_blocked: Sequence[str] | None = None) -> dict[str, Any]:
    """Verify one current session, and the previous qualified session when the chain has one."""
    import time
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
    # Queue first, from the small verified artifact, so the large decision file is read once.
    current_probe = _resolve_operation(root, registry, session, current_operation, deadline, set(), set(), stream=False)
    selection_blocker = current_probe["queue_blocker"]
    selection = None
    authority = "DAILY_OPPORTUNITY_DECISION_QUEUE"
    if selection_blocker is None:
        selection = select_from_queue(current_probe["queue"], lanes=lanes, tiers=tiers, max_tickers=max_tickers,
                                      include_tickers=include_tickers)
        full_names = [item["ticker"] for item in selection["selected"]]
        slim_names = []
        for lane in selection["lanes"]:
            for row in current_probe["queue"]["lane_queues"][lane["lane"]]["tickers"]:
                if row["lane_priority"] in tiers and (include_tickers is None or row["ticker"] in set(include_tickers)):
                    slim_names.append(row["ticker"])
        slim_names = list(dict.fromkeys(slim_names))
    elif explicit_tickers_when_queue_blocked:
        bounded.select_tickers(explicit_tickers_when_queue_blocked)
        full_names = list(bounded.select_tickers(explicit_tickers_when_queue_blocked))
        slim_names = list(full_names)
        authority = "EXPLICIT_TICKER_PREVIEW_QUEUE_BLOCKED"
        selection = {"lanes": [], "selected": [{"ticker": ticker, "primary_lane": None, "lanes": [], "lane_priority": None}
                                               for ticker in full_names], "overlaps": [], "cap_excluded": [],
                     "inclusion_exclusions": [], "queue_denominator": None, "qualified_count": None,
                     "unique_qualified_ticker_count": None, "selected_count": len(full_names)}
    else:
        raise ResearchFocusError(selection_blocker)
    full_set, slim_set = set(full_names), set(slim_names)
    current = _resolve_operation(root, registry, session, current_operation, deadline, full_set, slim_set, stream=True)
    previous = None
    if previous_session is not None:
        previous = _resolve_operation(root, registry, previous_session, previous_operation, deadline, full_set, slim_set)
    queue = current["queue"]
    opportunity_artifact = current["opportunity"]
    rows = []
    dossiers = []
    mismatches = []
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
    current_lineage = _priority_lineage(queue, current["metadata"])
    previous_lineage = None if previous is None else _priority_lineage(previous["queue"], previous["metadata"])
    require_current_record = current_lineage["status"] != "INTEGRATED_DECISION_BUILT_FROM_A_DIFFERENT_PRIORITY_QUEUE"
    require_previous_record = previous_lineage is None or previous_lineage["status"] != "INTEGRATED_DECISION_BUILT_FROM_A_DIFFERENT_PRIORITY_QUEUE"
    for item in selection["selected"]:
        ticker = item["ticker"]
        if authority != "DAILY_OPPORTUNITY_DECISION_QUEUE":
            decision = current["full"].get(ticker)
            if decision is None:
                mismatches.append({"ticker": ticker, "status": "INTEGRATED_DECISION_RECORD_ABSENT"})
                continue
            previous_row = previous["full"].get(ticker) if previous else None
            label = transitions[ticker]["transition"]
            confirmation = "GAINED_CONFIRMATION" if ticker in context["tactical_transition"]["gained_confirmation"] else (
                "RETAINED_CONFIRMATION" if ticker in context["tactical_transition"]["retained_confirmation"] else "NOT_IN_CONFIRMATION_DELTA")
            empty_queue = {"research_priority_tier": None, "entry_relevant": None, "priority_reasons": [],
                           "blocking_reasons": [], "invalidation_or_context_warnings": [], "lane_specific_priority": {},
                           "content_identity": None, "opportunity_record_content_identity": None, "authority_note": authority}
            dossier = _dossier(item, empty_queue, decision, previous_row, session=session, previous_session=previous_session,
                               transition_label=label, confirmation_status=confirmation, brief=context,
                               current_view=current_view, previous_view=previous_view)
            dossier["selection_authority"] = authority
            dossiers.append(dossier)
            rows.append(_overview_row(item, empty_queue, current["slim"].get(ticker), dossier["evolution"]["code"], None, deep=True))
            continue
        queue_record = queue["records"][ticker]
        opportunity_record = opportunity_artifact["records"].get(ticker) or {}
        decision = current["full"].get(ticker)
        binding = _bind(queue_record, decision or current["slim"].get(ticker), opportunity_record,
                        require_queue_record_identity=require_current_record)
        if binding["status"] != "BOUND" or decision is None:
            mismatches.append({"ticker": ticker, **binding})
            rows.append(_overview_row(item, queue_record, current["slim"].get(ticker), None, binding["status"], deep=False))
            continue
        previous_row = previous["full"].get(ticker) if previous else None
        if previous_row is not None and previous["queue"] is not None and require_previous_record:
            previous_queue = previous["queue"]["records"].get(ticker)
            if previous_queue is not None and (previous_row.get("source_identities") or {}).get("priority_queue_record_identity") != previous_queue.get("content_identity"):
                mismatches.append({"ticker": ticker, "status": "PREVIOUS_QUEUE_IDENTITY_MISMATCH"})
                rows.append(_overview_row(item, queue_record, current["slim"].get(ticker), None, "PREVIOUS_QUEUE_IDENTITY_MISMATCH", deep=False))
                continue
        confirmation = "GAINED_CONFIRMATION" if ticker in context["tactical_transition"]["gained_confirmation"] else (
            "RETAINED_CONFIRMATION" if ticker in context["tactical_transition"]["retained_confirmation"] else (
                "LOST_CONFIRMATION" if ticker in context["tactical_transition"]["lost_confirmation"] else "NOT_IN_CONFIRMATION_DELTA"))
        try:
            bounded.validate_price_dimensions(previous_row, decision)
            dossier = _dossier(item, queue_record, decision, previous_row, session=session, previous_session=previous_session,
                               transition_label=transitions[ticker]["transition"], confirmation_status=confirmation,
                               brief=context, current_view=current_view, previous_view=previous_view)
        except (ResearchFocusError, action_center.ActionCenterError, ValueError) as exc:
            mismatches.append({"ticker": ticker, "status": "DOSSIER_SOURCE_CONFLICT", "reason": str(exc)})
            rows.append(_overview_row(item, queue_record, current["slim"].get(ticker), None, "DOSSIER_SOURCE_CONFLICT", deep=False))
            continue
        if not require_current_record:
            dossier["source"]["priority_record_lineage"] = "UNBOUND_DIFFERENT_QUEUE_ARTIFACT"
        dossier["confirmation"]["tactical_entry_state"] = (None if ticker not in current["confirmed"] else "SOURCE_CONFIRMED_ENTRY_STATE")
        dossiers.append(dossier)
        rows.append(_overview_row(item, queue_record, current["slim"].get(ticker), dossier["evolution"]["code"], None, deep=True))
    # Qualified names that were not given a deep dossier still get a slim overview row.
    if authority == "DAILY_OPPORTUNITY_DECISION_QUEUE":
        deep = {row["ticker"] for row in rows}
        for ticker in slim_names:
            if ticker in deep:
                continue
            queue_record = queue["records"][ticker]
            opportunity_record = opportunity_artifact["records"].get(ticker) or {}
            binding = _bind(queue_record, current["slim"].get(ticker), opportunity_record,
                             require_queue_record_identity=require_current_record)
            lane = requested_lane(queue_record, lanes)
            item = {"ticker": ticker, "primary_lane": lane,
                    "lanes": [name for name in lanes if name in (queue_record.get("lane_specific_priority") or {})],
                    "lane_priority": (queue_record.get("lane_specific_priority") or {}).get(lane)}
            previous_slim = previous["slim"].get(ticker) if previous else None
            evolution = None
            if binding["status"] == "BOUND" and current["slim"].get(ticker) is not None:
                label = action_center._expected_posture_label(previous_slim, current["slim"][ticker], previous_view or {}, current_view)
                confirmation = "NOT_IN_CONFIRMATION_DELTA"
                evolution = _evolution(previous_slim, current["slim"][ticker], label, confirmation)["code"]
            rows.append(_overview_row(item, queue_record, current["slim"].get(ticker), evolution,
                                      None if binding["status"] == "BOUND" else binding["status"], deep=False))
            if binding["status"] != "BOUND":
                mismatches.append({"ticker": ticker, **binding, "scope": "OVERVIEW"})
    population = {
        "opportunity_queue_denominator": None if queue is None else len(queue["records"]),
        "opportunity_artifact_denominator": None if opportunity_artifact is None else len(opportunity_artifact["records"]),
        "integrated_decision_denominator": current["source_record_count"],
        "previous_integrated_decision_denominator": None if previous is None else previous["source_record_count"],
        "difference_interpretation": "DISTINCT_SOURCE_DEFINED_POPULATIONS_NOT_MISSING_LISTINGS",
    }
    passes = [{"role": "current_integrated_decision", "source_bytes": current["source_bytes"], "identity": current["source_identity"]},
              {"role": "current_queue", "source_bytes": current["queue_bytes"], "identity": None if queue is None else queue.get("artifact_identity")},
              {"role": "current_opportunity", "source_bytes": current["opportunity_bytes"],
               "identity": None if opportunity_artifact is None else opportunity_artifact.get("artifact_identity")}]
    if previous is not None:
        passes.insert(0, {"role": "previous_integrated_decision", "source_bytes": previous["source_bytes"], "identity": previous["source_identity"]})
    lineage_unbound = current_lineage["status"] == "INTEGRATED_DECISION_BUILT_FROM_A_DIFFERENT_PRIORITY_QUEUE" or (
        previous_lineage is not None and previous_lineage["status"] == "INTEGRATED_DECISION_BUILT_FROM_A_DIFFERENT_PRIORITY_QUEUE")
    if selection_blocker:
        status = "SELECTION_BLOCKED_EXPLICIT_PREVIEW"
    elif mismatches:
        status = "SOURCE_IDENTITY_MISMATCHES"
    elif lineage_unbound:
        status = "LANE_SELECTION_QUALIFIED_PRIORITY_RECORD_LINEAGE_UNBOUND"
    else:
        status = "COMPLETE"
    body = {
        "contract_version": CONTRACT, "session": session, "previous_qualified_session": previous_session,
        "selection_authority": authority, "selection_blocker": selection_blocker, "status": status,
        "requested_lanes": list(lanes) if authority == "DAILY_OPPORTUNITY_DECISION_QUEUE" else [],
        "requested_tiers": list(tiers) if authority == "DAILY_OPPORTUNITY_DECISION_QUEUE" else [],
        "max_tickers": max_tickers, "population": population, "lane_reports": [] if selection is None else selection["lanes"],
        "overlaps": [] if selection is None else selection["overlaps"],
        "cap_excluded": [] if selection is None else selection["cap_excluded"],
        "inclusion_exclusions": [] if selection is None else selection["inclusion_exclusions"],
        "qualified_count": None if selection is None else selection["qualified_count"],
        "unique_qualified_ticker_count": None if selection is None else selection.get("unique_qualified_ticker_count"),
        "selected_count": 0 if selection is None else selection["selected_count"],
        "overview": rows, "dossiers": dossiers, "identity_mismatches": mismatches,
        "statistics": _statistics(rows, dossiers),
        "priority_lineage": {"current": current_lineage, "previous": previous_lineage},
        "verification_passes": passes,
        "verification": "FULL_NATIVE_CONTENT_VERIFIED",
        "authority_boundary": {
            "is_actionable": False, "authority_effect": "NONE", "research_only": True,
            "no_score_vote_fair_value_target_or_execution": True,
            "private_portfolio": "NOT_REQUESTED_OR_READ",
        },
    }
    body.update(content_identity(body))
    return body


def requested_lane(queue_record: Mapping[str, Any], lanes: Sequence[str]) -> str:
    for lane in lanes:
        if lane in (queue_record.get("lane_specific_priority") or {}):
            return lane
    return lanes[0]


def render_markdown(artifact: Mapping[str, Any]) -> str:
    if artifact.get("contract_version") != CONTRACT or any(artifact.get(key) != value for key, value in content_identity(artifact).items()):
        raise ResearchFocusError("RENDER_CONTRACT_OR_IDENTITY_MISMATCH")
    population = artifact["population"]
    lines = ["# Trọng tâm nghiên cứu", "",
             f"Phiên {artifact['session']}. Phiên đủ điều kiện trước đó: {artifact['previous_qualified_session'] or 'KHÔNG CÓ'}.",
             f"Làn yêu cầu: {', '.join(artifact['requested_lanes']) or 'KHÔNG CÓ — lựa chọn làn bị chặn'}.",
             f"Mẫu số hàng đợi cơ hội: {population['opportunity_queue_denominator']}. Mẫu số quyết định tích hợp: {population['integrated_decision_denominator']}.",
             "Hai mẫu số là hai quần thể nguồn khác nhau. Chênh lệch không có nghĩa mã bị thiếu hoặc phân tích thất bại.",
             f"Ứng viên đủ lọc theo từng làn, cộng lại và có thể trùng mã: {artifact['qualified_count']}. Mã duy nhất: {artifact.get('unique_qualified_ticker_count')}. Hồ sơ sâu: {artifact['selected_count']}. Trạng thái: {artifact['status']}.",
             "Đây là bảng chú ý nghiên cứu, không phải khuyến nghị giao dịch, không phải điểm số và không phải lệnh thực hiện.",
             ""]
    lineage = (artifact.get("priority_lineage") or {}).get("current") or {}
    if lineage.get("status") == "INTEGRATED_DECISION_BUILT_FROM_A_DIFFERENT_PRIORITY_QUEUE":
        lines.append("Quyết định tích hợp được dựng từ một hàng đợi ưu tiên khác với hàng đợi đầu ra của phiên.")
        lines.append("Danh tính bản ghi không được ghép. Tầng ưu tiên nhúng vẫn được đối chiếu riêng. Không suy ra cùng một bản ghi.")
        lines.append("Hàng đợi phiên: " + str(lineage.get("operation_queue_identity")))
        lines.append("Hàng đợi trong quyết định: " + str(lineage.get("integrated_decision_priority_queue_identity")))
        lines.append("")
    if artifact.get("selection_blocker"):
        lines.append("Chặn lựa chọn làn: " + artifact["selection_blocker"])
        lines.append("")
    for lane in artifact["lane_reports"]:
        lines.append(f"## Làn {lane['lane']}")
        lines.append(lane["objective"])
        lines.append(f"Nguồn {lane['source_count']} mã; sau lọc {lane['qualified_count']}; hồ sơ sâu {len(lane['selected_tickers'])}.")
        lines.append("Thứ tự gốc: " + ", ".join(lane["selected_tickers"]) if lane["selected_tickers"] else "Không chọn thêm mã trong giới hạn.")
        lines.append("")
    lines.append("## Danh sách chú ý")
    for row in artifact["overview"]:
        marker = "hồ sơ sâu" if row["deep_dossier"] else "chỉ mức chú ý"
        lines.append(f"- {row['ticker']} | {row['primary_lane']} | {row['lane_priority']} | tư thế {row['research_action_posture']} | {row['evolution']} | {marker} | {row['one_reason']}")
    lines.append("")
    for dossier in artifact["dossiers"]:
        summary = dossier["summary"]
        lines.extend([
            f"## {dossier['ticker']}", "",
            f"Tóm tắt: {summary['why_inspect'] or 'Nguồn không có câu why_now.'}",
            f"Được chọn vì làn {summary.get('lane_objective')} Ưu tiên {summary['research_priority_tier']}, mức trong làn {summary['lane_priority']}. Tư thế chuẩn {summary['research_action_posture']}. Hai thứ này không phải một lệnh.",
            f"Diễn biến mô tả: {summary['evolution']}. Trạng thái trực giao nguồn: {summary['coherence_state']}.",
            "### Kỹ thuật, thị trường, ngành",
            f"Pha {dossier['tactical_market_sector']['tactical_phase']}; cấu trúc {dossier['tactical_market_sector']['market_structure_state']}; phá nền {dossier['tactical_market_sector']['breakout_state_v3']}.",
            f"Chế độ thị trường {(dossier['tactical_market_sector']['market_sector_context'] or {}).get('market_regime')}; ngành {(dossier['tactical_market_sector']['market_sector_context'] or {}).get('sector_leadership')}. Yếu thị trường là bối cảnh, không phải phủ quyết mới.",
            "### Cơ bản và định giá",
            f"Cơ bản {dossier['fundamental']['fundamental_state']}; mức sẵn có {dossier['fundamental']['fundamental_evidence_availability']}. Thiếu dữ liệu không phải tín hiệu kinh doanh xấu. Một kỳ ngắn không phải luận điểm cấu trúc.",
            f"Định giá {dossier['valuation']['status']}; so với nhóm {dossier['valuation']['peer_relative_state']}. Không có giá trị hợp lý, biên an toàn hay giá mục tiêu. Vốn hóa chỉ là quy mô.",
            "### Sự kiện",
            f"Trạng thái {dossier['corporate']['state']}; phiên bằng chứng {dossier['corporate']['evidence_session']}; cũ hơn phiên quyết định: {dossier['corporate']['evidence_session_stale']}.",
            "### Luận điểm và phản luận điểm",
            "Ủng hộ: " + "; ".join(str(item) for item in dossier["thesis"]["supporting"][:8]),
            "Phản đối hoặc chặn: " + "; ".join(str(item) for item in dossier["thesis"]["opposing"][:8]),
            "Không chắc: " + "; ".join(str(item) for item in dossier["thesis"]["uncertain"][:6]),
            "### Xác nhận và vô hiệu",
            f"Xác nhận đã quan sát: {dossier['confirmation']['observed_confirmation']}. Điều kiện tương lai không phải sự kiện đã xảy ra: {dossier['confirmation']['future_trigger_is_not_an_observed_event']}.",
            f"Nhãn chuyển tiếp nguồn: {dossier['setup_transition'].get('governed_transition_label')}. Nhãn này không phải kết quả đầu tư đã đo.",
            "### Câu hỏi nghiên cứu tiếp",
        ])
        for question in dossier["research_questions"][:6]:
            lines.append(f"- {question['question']} ({question['source_code']})")
        lines.append(f"Nguồn quyết định {dossier['source']['decision_identity']}.")
        lines.append("")
    if artifact["identity_mismatches"]:
        lines.append("## Lệch danh tính nguồn")
        for item in artifact["identity_mismatches"]:
            lines.append(f"- {item['ticker']}: {item['status']}")
    lines.append("")
    lines.append("Ranh giới: nghiên cứu có kiểm chứng, không đủ điều kiện thực hiện lệnh.")
    return "\n".join(lines) + "\n"
