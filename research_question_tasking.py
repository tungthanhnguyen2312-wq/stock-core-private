"""Deterministic, immutable research-question tasks derived from research dossiers.

This module is a research-workflow consumer.  It does not collect evidence, decide
authority, or allow AI prose to resolve a factual question.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _task_id(ticker: str, kind: str, question: Mapping[str, Any]) -> str:
    semantic_key = {"ticker": ticker, "kind": kind, "claim": question["claim"],
                    "evidence_field": question["evidence_field"]}
    return "research_task:" + _hash(semantic_key)


def _deferred_reason(warnings: list[str]) -> tuple[str | None, str | None]:
    known = {
        "LIQUIDITY_SIZING_BLOCKED": (
            "QUALIFIED_LIQUIDITY_INPUTS_NOT_AVAILABLE",
            "new qualified market-wide volume/traded-value composition evidence under its existing contract",
        ),
        "HISTORICAL_PIT_NOT_ELIGIBLE": (
            "HISTORICAL_PIT_NOT_PROMOTED",
            "new qualified historical RAW_AS_TRADED and corporate-action event-window evidence",
        ),
        "ACTIVE_UNIVERSE_NOT_PROMOTED": (
            "ACTIVE_UNIVERSE_AUTHORITY_UNKNOWN",
            "new verified exchange/listing-status evidence under the canonical-universe contract",
        ),
        "PROVIDER_FUNDAMENTALS_DESCRIPTIVE_ONLY": (
            "PROVIDER_CROSS_METRIC_SEMANTICS_CLOSED",
            "new independently qualified semantic evidence; no automatic provider retry",
        ),
    }
    for warning in warnings:
        if warning in known:
            return known[warning]
    return None, None


def _question_spec(dossier: Mapping[str, Any], question: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": "QUESTION_TO_VERIFY",
        "question": question,
        "authority_tier": "SHADOW_ONLY",
        "reason_matters": "Issuer-specific context is needed before interpreting the retained technical state.",
        "expected_evidence_type": "cited issuer-specific evidence that can be linked to the existing deterministic state",
        "researchability": "HUMAN_REVIEW_WITH_CITED_EVIDENCE_ONLY",
        "status": "OPEN",
        "deferred_reason": None,
        "reopen_condition": None,
    }


def _gap_spec(dossier: Mapping[str, Any], gap: Mapping[str, Any]) -> dict[str, Any]:
    # The gap itself takes precedence over co-occurring general warnings.  A liquidity
    # gap must point to the liquidity contract's reopen condition, not merely the
    # first unrelated blocker recorded on the dossier.
    warnings = list(dossier["warnings"])
    if "Liquidity sizing" in gap["claim"] and "LIQUIDITY_SIZING_BLOCKED" in warnings:
        warnings = ["LIQUIDITY_SIZING_BLOCKED"] + [warning for warning in warnings if warning != "LIQUIDITY_SIZING_BLOCKED"]
    deferred_reason, reopen_condition = _deferred_reason(warnings)
    return {
        "kind": "DATA_GAP",
        "question": {"claim": gap["claim"], "evidence_field": gap["evidence_field"], "type": "DATA_GAP"},
        "authority_tier": gap["authority"],
        "reason_matters": "The research product must not imply execution capacity while this gap remains blocked.",
        "expected_evidence_type": "qualified market-wide liquidity/traded-value semantics and execution-capacity inputs",
        "researchability": "NO_CURRENT_AUTOMATIC_EVIDENCE_ROUTE" if deferred_reason else "HUMAN_REVIEW_WITH_CITED_EVIDENCE_ONLY",
        "status": "DEFERRED_NO_CURRENT_EVIDENCE_ROUTE" if deferred_reason else "OPEN",
        "deferred_reason": deferred_reason,
        "reopen_condition": reopen_condition,
    }


def _resolution_status(spec: Mapping[str, Any], evidence: Mapping[str, Any] | None) -> tuple[str, str]:
    """Return status only when an external deterministic authority check explicitly passes."""
    if not evidence:
        return spec["status"], "NO_NEW_EVIDENCE"
    if evidence.get("conflict"):
        return "OPEN", "EVIDENCE_CONFLICT_REMAINS_UNRESOLVED"
    if not evidence.get("contract_satisfied"):
        return spec["status"], "EVIDENCE_NOT_QUALIFIED_FOR_TASK_RESOLUTION"
    if evidence.get("authority") == "OFFICIAL_QUALIFIED":
        return "RESOLVED_BY_QUALIFIED_EVIDENCE", "EXISTING_QUALIFIED_CONTRACT_SATISFIED"
    if evidence.get("authority") in {"PROVIDER_RESEARCH", "DERIVED_PROXY", "SHADOW_ONLY"} and evidence.get("descriptive_resolution_allowed"):
        return "RESOLVED_DESCRIPTIVELY", "LOWER_AUTHORITY_DESCRIPTIVE_RESOLUTION"
    return spec["status"], "AUTHORITY_INSUFFICIENT_FOR_TASK_RESOLUTION"


def _state(spec: Mapping[str, Any], dossier: Mapping[str, Any], previous: Mapping[str, Any] | None,
           evidence: Mapping[str, Any] | None) -> dict[str, Any]:
    task_id = _task_id(dossier["ticker"], spec["kind"], spec["question"])
    status, status_basis = _resolution_status(spec, evidence)
    if previous and previous["task_status"] not in {"SUPERSEDED_BY_NEW_QUESTION", "CLOSED_NOT_MATERIAL"} and not evidence:
        # Replay must preserve the historical state identity rather than manufacture a
        # new status-basis event merely because the same dossier was read again.
        status, status_basis = previous["task_status"], previous["status_basis"]
    prior_lineage = list(previous["status_change_lineage"]) if previous else []
    if not prior_lineage or prior_lineage[-1]["status"] != status:
        prior_lineage.append({"status": status, "basis": status_basis,
                              "research_session": dossier["research_session"]})
    state = {
        "schema_version": "1.0.0",
        "contract_version": "research_question_tasking/v1",
        "task_identity": task_id,
        "ticker": dossier["ticker"],
        "task_kind": spec["kind"],
        "originating_dossier_identity": previous["originating_dossier_identity"] if previous else dossier["dossier_identity"],
        "current_dossier_identity": dossier["dossier_identity"],
        "originating_research_session": previous["originating_research_session"] if previous else dossier["research_session"],
        "current_research_session": dossier["research_session"],
        "question": spec["question"],
        "question_hash": _hash(spec["question"]),
        "related_warning_identifiers": list(dossier["warnings"]),
        "authority_tier": spec["authority_tier"],
        "related_fundamental_authority": dossier["authority_evidence_tiers"]["fundamental_context"],
        "thesis_hash": dossier["thesis_hash"],
        "counter_thesis_hash": dossier["counter_thesis_hash"],
        "evidence_paths": dossier["evidence_paths"],
        "reason_matters": spec["reason_matters"],
        "expected_evidence_type": spec["expected_evidence_type"],
        "researchability": spec["researchability"],
        "task_status": status,
        "status_basis": status_basis,
        "deferred_reason": spec["deferred_reason"],
        "reopen_condition": spec["reopen_condition"],
        "created_at_semantics": "originating_research_session",
        "updated_at_semantics": "current_research_session_when_state_changes",
        "created_at": previous["created_at"] if previous else dossier["research_session"],
        "updated_at": dossier["research_session"] if not previous or previous["task_status"] != status else previous["updated_at"],
        "status_change_lineage": prior_lineage,
        "ai_resolution_authority": False,
    }
    state["task_state_identity"] = "research_task_state:" + _hash(state)
    return state


def _superseded_state(previous: Mapping[str, Any], successor_id: str) -> dict[str, Any]:
    state = dict(previous)
    lineage = list(previous["status_change_lineage"])
    if previous["task_status"] != "SUPERSEDED_BY_NEW_QUESTION":
        lineage.append({"status": "SUPERSEDED_BY_NEW_QUESTION", "basis": "QUESTION_SEMANTIC_IDENTITY_CHANGED",
                        "research_session": previous["current_research_session"]})
    state.update({"task_status": "SUPERSEDED_BY_NEW_QUESTION", "status_basis": "QUESTION_SEMANTIC_IDENTITY_CHANGED",
                  "superseded_by_task_identity": successor_id, "status_change_lineage": lineage})
    state.pop("task_state_identity", None)
    state["task_state_identity"] = "research_task_state:" + _hash(state)
    return state


def _missing_dossier_state(previous: Mapping[str, Any]) -> dict[str, Any]:
    """Keep task history visible when an input dossier is absent from a later run."""
    state = dict(previous)
    state["dossier_presence"] = "MISSING_FROM_CURRENT_RUN"
    state.pop("task_state_identity", None)
    state["task_state_identity"] = "research_task_state:" + _hash(state)
    return state


def build(dossiers: Mapping[str, Mapping[str, Any]], *,
          previous_by_task: Mapping[str, Mapping[str, Any]] | None = None,
          evidence_by_task: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Derive task states. Previous task versions are read-only; absent evidence never resolves."""
    previous_by_task = previous_by_task or {}
    evidence_by_task = evidence_by_task or {}
    tasks: list[dict[str, Any]] = []
    active_ids: set[str] = set()
    active_by_ticker_kind: dict[tuple[str, str], str] = {}
    for dossier in sorted(dossiers.values(), key=lambda row: row["ticker"]):
        specs = [_question_spec(dossier, question) for question in dossier["open_questions"]]
        specs.extend(_gap_spec(dossier, gap) for gap in dossier["data_gaps"])
        for spec in specs:
            task_id = _task_id(dossier["ticker"], spec["kind"], spec["question"])
            active_ids.add(task_id)
            active_by_ticker_kind[(dossier["ticker"], spec["kind"])] = task_id
            tasks.append(_state(spec, dossier, previous_by_task.get(task_id), evidence_by_task.get(task_id)))
    # A semantic question replacement creates a successor; it never overwrites task history.
    for task_id, previous in sorted(previous_by_task.items()):
        successor = active_by_ticker_kind.get((previous["ticker"], previous["task_kind"]))
        if task_id not in active_ids and successor and successor != task_id:
            tasks.append(_superseded_state(previous, successor))
        elif task_id not in active_ids and previous["ticker"] not in dossiers:
            tasks.append(_missing_dossier_state(previous))

    queue = []
    for task in tasks:
        if task["task_kind"] != "QUESTION_TO_VERIFY" or not dossiers.get(task["ticker"], {}).get("ai_queue_member"):
            continue
        queue.append({"task_identity": task["task_identity"], "ticker": task["ticker"],
                      "priority_reasons": ["PRESERVED_DETERMINISTIC_AI_RESEARCH_QUEUE_MEMBERSHIP", "OPEN_QUESTION"],
                      "originating_dossier_identity": task["originating_dossier_identity"],
                      "question": task["question"], "authority_tier": task["authority_tier"],
                      "evidence_paths": task["evidence_paths"], "expected_evidence_type": task["expected_evidence_type"],
                      "not_a_recommendation": True})
    queue.sort(key=lambda row: row["ticker"])
    status_counts: dict[str, int] = {}
    authority_counts: dict[str, int] = {}
    for task in tasks:
        status_counts[task["task_status"]] = status_counts.get(task["task_status"], 0) + 1
        authority_counts[task["authority_tier"]] = authority_counts.get(task["authority_tier"], 0) + 1
    artifact = {
        "schema_version": "1.0.0",
        "contract_version": "research_question_tasking/v1",
        "source_dossier_count": len(dossiers),
        "source_dossier_identities": {ticker: dossier["dossier_identity"] for ticker, dossier in sorted(dossiers.items())},
        "tasks": tasks,
        "priority_queue": queue,
        "coverage": {"dossiers_dispositioned": len(dossiers), "total_tasks": len(tasks),
                     "status_counts": status_counts, "authority_tier_counts": authority_counts,
                     "ai_queue_dossier_count": sum(dossier["ai_queue_member"] for dossier in dossiers.values()),
                     "ai_queue_task_coverage": len(queue),
                     "deferred_no_current_route_count": status_counts.get("DEFERRED_NO_CURRENT_EVIDENCE_ROUTE", 0)},
        "authority_boundary": {"ai_may_not_resolve_tasks": True, "new_evidence_acquisition": "NOT_PERFORMED",
                               "recommendations_targets_probabilities": "NOT_EMITTED", "authority_promotion": "NOT_PERFORMED"},
        "verdict": "RESEARCH_QUESTION_TASKING_V1_READY",
    }
    artifact["artifact_sha256"] = _hash(artifact)
    artifact["artifact_identity"] = "research_question_tasking_run:" + artifact["artifact_sha256"]
    return artifact


def write_immutable(path: Path, value: Mapping[str, Any]) -> None:
    payload = _canon(value) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != payload:
        raise ValueError("IMMUTABLE_RESEARCH_TASK_CONTENT_CONFLICT")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def load_latest_tasks(root: Path) -> dict[str, dict[str, Any]]:
    index_path = root / "latest_task_state_index.json"
    if not index_path.exists():
        return {}
    index = json.loads(index_path.read_text(encoding="utf-8"))
    return {task_id: json.loads((root / relative).read_text(encoding="utf-8"))
            for task_id, relative in index["task_state_paths"].items()}


def write_task_states(root: Path, artifact: Mapping[str, Any]) -> int:
    paths: dict[str, str] = {}
    written = 0
    for task in artifact["tasks"]:
        digest = task["task_state_identity"].split(":", 1)[1]
        relative = Path("versions") / task["task_identity"].split(":", 1)[1] / f"{digest}.json"
        path = root / relative
        if not path.exists():
            written += 1
        write_immutable(path, task)
        paths[task["task_identity"]] = relative.as_posix()
    index = {"schema_version": "1.0.0", "contract_version": "research_question_tasking/v1",
             "task_state_paths": dict(sorted(paths.items()))}
    (root / "latest_task_state_index.json").write_text(_canon(index) + "\n", encoding="utf-8")
    return written


def markdown(artifact: Mapping[str, Any]) -> str:
    lines = ["# Research Question Follow-up Queue", "", "## Human research tasks (not recommendations)"]
    for task in artifact["priority_queue"]:
        lines.append(f"- {task['ticker']}: {task['question']['claim']} [{', '.join(task['priority_reasons'])}]")
    return "\n".join(lines) + "\n"
