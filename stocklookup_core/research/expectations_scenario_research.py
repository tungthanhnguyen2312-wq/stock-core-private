"""Evidence-bound scenario research over immutable daily research state.

Scenario lanes organize retained evidence for human review; they do not forecast,
assign probabilities, price targets, or recommendation authority.
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


def _item(kind: str, claim: str, authority: str, evidence: str) -> dict[str, Any]:
    return {"classification": kind, "claim": claim, "authority_tier": authority, "evidence_reference": evidence}


def _content(review: Mapping[str, Any], dossier: Mapping[str, Any], task: Mapping[str, Any],
             relative: Mapping[str, Any] | None) -> dict[str, Any]:
    facts = [_item("FACT", f"Retained {fact['field']} is available for the completed research session.",
                   fact["authority"], fact["evidence_path"]) for fact in review["facts"]]
    inferences = [_item("INFERENCE", f"Retained {item['category']} is {item['value']}.", item["authority"], item["evidence_path"])
                  for item in review["inferences"]]
    gaps = [_item("DATA_GAP", gap["claim"], gap["authority"], gap["evidence_field"])
            for gap in review["data_gaps"]]
    thesis = [_item(item["type"], item["claim"], item["authority"], item["evidence_field"])
              for item in dossier["thesis"]]
    counter = [_item(item["type"], item["claim"], item["authority"], item["evidence_field"])
               for item in dossier["counter_thesis"]]
    trend = dossier["deterministic_research_state"]["inferences"][0]["value"]
    invalidation = ({"status": "STATE_DETERIORATION", "condition": "A later retained state is AT_OR_BELOW_MA20 after this above-MA20 state.",
                     "classification": "HYPOTHESIS", "evidence_reference": "deterministic_inferences.trend_state"}
                    if trend == "ABOVE_MA20" else
                    {"status": "UNRESOLVED", "condition": "No adequate retained deterministic invalidation condition is available.",
                     "classification": "DATA_GAP", "evidence_reference": "deterministic_inferences.trend_state"})
    question_invalidation = {"status": "QUESTION_RESOLVED_AGAINST_THESIS", "state": "CONDITIONAL_NOT_OBSERVED",
                             "condition": "A future qualified or permitted descriptive task resolution against a thesis premise requires human thesis review.",
                             "classification": "HYPOTHESIS", "task_identity": task["task_identity"],
                             "evidence_reference": task["question"]["evidence_field"]}
    discriminating = [{"classification": "QUESTION_TO_VERIFY", "claim": task["question"]["claim"],
                        "task_identity": task["task_identity"], "evidence_reference": task["question"]["evidence_field"]}]
    content = {
        "schema_version": "1.0.0", "contract_version": "expectations_scenario_research/v1",
        "ticker": review["ticker"], "research_session": dossier["research_session"],
        "originating_dossier_identity": dossier["dossier_identity"], "evidence_authority_summary": dossier["authority_evidence_tiers"],
        "current_observable_state": {"facts": facts, "research_inferences": inferences,
                                     "relative_context": relative["relative_metrics"] if relative else [],
                                     "relative_context_identity": relative["source_lineage"]["relative_context"] if relative else None},
        "thesis_reference": {"hash": dossier["thesis_hash"], "items": thesis},
        "counter_thesis_reference": {"hash": dossier["counter_thesis_hash"], "items": counter},
        "expectations": {"OBSERVED_STATE": facts, "RESEARCH_INFERENCE": inferences,
                         "EXPLICIT_EXTERNAL_EXPECTATION": {"status": "UNAVAILABLE", "reason": "NO_RETAINED_QUALIFIED_EXTERNAL_EXPECTATION"},
                         "MARKET_IMPLIED_EXPECTATION": {"status": "UNAVAILABLE", "reason": "NO_APPROVED_DETERMINISTIC_IMPLIED_EXPECTATION_MODEL"},
                         "VARIANT_HYPOTHESIS": {"status": "UNAVAILABLE", "reason": "NO_RETAINED_PREVAILING_EXPECTATION_FOR_COMPARISON"}},
        "probability_status": "UNQUALIFIED",
        "scenarios": {
            "BEAR": {"drivers": counter or gaps, "observable_evidence": counter or gaps, "evidence_still_missing": gaps,
                     "catalysts": [{"status": "NO_EVIDENCE_BACKED_CATALYST"}], "invalidation_or_reversal_conditions": [invalidation, question_invalidation]},
            "BASE": {"drivers": facts, "observable_evidence": facts, "evidence_still_missing": gaps,
                     "catalysts": [{"status": "NO_EVIDENCE_BACKED_CATALYST"}], "invalidation_or_reversal_conditions": [invalidation, question_invalidation]},
            "BULL": {"drivers": thesis or [_item("DATA_GAP", "No positive deterministic thesis is retained.", "BLOCKED", "thesis_reference")],
                     "observable_evidence": thesis or [], "evidence_still_missing": gaps,
                     "catalysts": [{"status": "NO_EVIDENCE_BACKED_CATALYST"}], "invalidation_or_reversal_conditions": [invalidation, question_invalidation]},
        },
        "cross_scenario_discriminating_variables": discriminating,
        "upcoming_observations_questions": discriminating,
        "material_uncertainties": gaps,
        "scenario_data_gaps": gaps,
        "relevant_research_task_identities": [task["task_identity"]],
        "invalidation_contract": {"allowed_statuses": ["EVIDENCE_INVALIDATION", "STATE_DETERIORATION", "QUESTION_RESOLVED_AGAINST_THESIS", "UNRESOLVED"],
                                  "automatic_thesis_breaking": False},
        "scenario_qualification_status": "PARTIAL_EVIDENCE_BOUND_SCENARIO",
        "authority_boundary": {"probabilities": "UNQUALIFIED", "targets_expected_returns_recommendations": "NOT_EMITTED",
                               "ai_may_not_add_evidence_or_resolve_tasks": True},
    }
    content["scenario_content_identity"] = "scenario_content:" + _hash(content)
    return content


def _version(content: Mapping[str, Any], previous: Mapping[str, Any] | None) -> dict[str, Any]:
    if previous and previous["scenario_content_identity"] == content["scenario_content_identity"]:
        return dict(previous)
    version = dict(content)
    version["prior_scenario_content_identity"] = previous["scenario_content_identity"] if previous else None
    version["scenario_version_identity"] = "scenario_version:" + _hash(version)
    return version


def build(review_pack: Mapping[str, Any], dossiers: Mapping[str, Mapping[str, Any]],
          tasks: Mapping[str, Mapping[str, Any]], relative_overlay: Mapping[str, Any], *,
          previous_by_ticker: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    previous_by_ticker = previous_by_ticker or {}
    relative = {entry["ticker"]: entry for entry in relative_overlay["review_entries"]}
    question_tasks = {task["ticker"]: task for task in tasks.values() if task["task_kind"] == "QUESTION_TO_VERIFY"}
    scenarios = []
    for review in review_pack["owner_review_queue"]:
        ticker = review["ticker"]
        scenarios.append(_version(_content(review, dossiers[ticker], question_tasks[ticker], relative.get(ticker)), previous_by_ticker.get(ticker)))
    counts: dict[str, int] = {}
    driver_classes: dict[str, int] = {}
    relative_used = 0
    for scenario in scenarios:
        counts[scenario["scenario_qualification_status"]] = counts.get(scenario["scenario_qualification_status"], 0) + 1
        relative_used += bool(scenario["current_observable_state"]["relative_context"])
        for lane in scenario["scenarios"].values():
            for driver in lane["drivers"]:
                driver_classes[driver["classification"]] = driver_classes.get(driver["classification"], 0) + 1
    artifact = {"schema_version": "1.0.0", "contract_version": "expectations_scenario_research/v1",
                "research_session": review_pack["run_summary"]["research_session"],
                "source_artifact_identities": {"review_pack": review_pack["artifact_identity"],
                                                "relative_context_overlay": relative_overlay["artifact_identity"]},
                "scenarios": scenarios,
                "coverage": {"attempted_cases": len(scenarios), "fully_structured_cases": 0,
                             "partial_cases": counts.get("PARTIAL_EVIDENCE_BOUND_SCENARIO", 0), "unavailable_cases": 0,
                             "qualification_counts": counts, "driver_classification_counts": driver_classes,
                             "catalyst_available_count": 0,
                             "invalidation_available_count": sum(s["scenarios"]["BULL"]["invalidation_or_reversal_conditions"][0]["status"] != "UNRESOLVED" for s in scenarios),
                             "relative_context_used_count": relative_used,
                             "external_expectation_available_count": 0, "market_implied_expectation_available_count": 0},
                "authority_boundary": {"research_shadow_only": True, "probability_status": "UNQUALIFIED",
                                       "recommendations_targets_expected_returns": "NOT_EMITTED", "scenario_grading": "NOT_IMPLEMENTED"},
                "verdict": "EXPECTATIONS_SCENARIO_RESEARCH_V1_READY"}
    artifact["artifact_sha256"] = _hash(artifact)
    artifact["artifact_identity"] = "expectations_scenario_research:" + artifact["artifact_sha256"]
    return artifact


def write_immutable(path: Path, scenario: Mapping[str, Any]) -> None:
    payload = _canon(scenario) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != payload:
        raise ValueError("IMMUTABLE_SCENARIO_CONTENT_CONFLICT")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def load_latest(root: Path) -> dict[str, dict[str, Any]]:
    index = root / "latest_scenario_index.json"
    if not index.exists():
        return {}
    values = json.loads(index.read_text(encoding="utf-8"))
    return {ticker: json.loads((root / path).read_text(encoding="utf-8")) for ticker, path in values["paths"].items()}


def write_versions(root: Path, artifact: Mapping[str, Any]) -> int:
    paths: dict[str, str] = {}; written = 0
    for scenario in artifact["scenarios"]:
        digest = scenario["scenario_version_identity"].split(":", 1)[1]
        relative = Path("versions") / scenario["ticker"] / f"{digest}.json"
        if not (root / relative).exists(): written += 1
        write_immutable(root / relative, scenario)
        paths[scenario["ticker"]] = relative.as_posix()
    (root / "latest_scenario_index.json").write_text(_canon({"schema_version": "1.0.0", "paths": dict(sorted(paths.items()))}) + "\n", encoding="utf-8")
    return written


def review_pack_overlay(review_pack: Mapping[str, Any], scenarios: Mapping[str, Any]) -> dict[str, Any]:
    by_ticker = {scenario["ticker"]: scenario for scenario in scenarios["scenarios"]}
    entries = []
    for review in review_pack["owner_review_queue"]:
        scenario = by_ticker[review["ticker"]]
        entries.append({"ticker": review["ticker"], "scenario_content_identity": scenario["scenario_content_identity"],
                        "current_state": scenario["current_observable_state"]["research_inferences"],
                        "bear_driver": scenario["scenarios"]["BEAR"]["drivers"][0],
                        "base_driver": scenario["scenarios"]["BASE"]["drivers"][0],
                        "bull_driver": scenario["scenarios"]["BULL"]["drivers"][0],
                        "strongest_counter_thesis": scenario["counter_thesis_reference"]["items"][0] if scenario["counter_thesis_reference"]["items"] else None,
                        "primary_question": scenario["cross_scenario_discriminating_variables"][0],
                        "invalidation": scenario["scenarios"]["BULL"]["invalidation_or_reversal_conditions"][0],
                        "evidence_quality": scenario["evidence_authority_summary"],
                        "scenario_qualification_status": scenario["scenario_qualification_status"]})
    overlay = {"schema_version": "1.0.0", "contract_version": "scenario_review_pack_overlay/v1",
               "base_review_pack_identity": review_pack["artifact_identity"], "scenario_artifact_identity": scenarios["artifact_identity"],
               "entries": entries, "verdict": "SCENARIO_REVIEW_PACK_OVERLAY_READY"}
    overlay["artifact_sha256"] = _hash(overlay)
    overlay["artifact_identity"] = "scenario_review_pack_overlay:" + overlay["artifact_sha256"]
    return overlay


def markdown(overlay: Mapping[str, Any]) -> str:
    lines = ["# Scenario & Expectations Review Context", ""]
    for entry in overlay["entries"]:
        lines.extend([f"## {entry['ticker']}", f"- Bear: {entry['bear_driver']['claim']}",
                      f"- Base: {entry['base_driver']['claim']}", f"- Bull: {entry['bull_driver']['claim']}",
                      f"- Question: {entry['primary_question']['claim']}",
                      f"- Invalidation: {entry['invalidation']['status']}"])
    return "\n".join(lines) + "\n"
