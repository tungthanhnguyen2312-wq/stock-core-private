"""Pure, fail-closed comparison of two qualified historical research briefs.

The comparison is deliberately snapshot-input only: callers must supply both briefs and
their identities are hashes of the supplied semantic payloads.  It neither reads live
data nor interprets narrative prose as a signal.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any, Mapping


SCHEMA_VERSION = "1.0.0"
ENGINE_VERSION = "phase-5d/1.0.0"
_PILOT_TICKERS = frozenset({"HPG", "VNM", "VCB"})
_SEMANTIC_FLAGS = {"analysis_mode": "historical_only_qualified_data", "historical_only": True, "is_actionable": False}
_FACT_IDENTITY = ("canonical_metric", "reporting_period", "statement_scope", "currency", "unit_scale")
_QUALITY_DIRECTION = {("unavailable", "available"): "improved", ("available", "unavailable"): "deteriorated"}
_PRIORITY = {"eligibility": 1, "invalidation": 2, "conclusion": 3, "fundamental_risk": 4, "quality": 5, "risk": 5, "scenario": 6, "fact": 7, "evidence": 7}


def _m(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _stable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)


def _sha(value: Any) -> str:
    return sha256(_stable(value).encode("utf-8")).hexdigest()


def _snapshot(brief: Mapping[str, Any]) -> dict[str, Any] | None:
    if not brief:
        return None
    identity = _m(brief.get("identity"))
    return {"schema_version": brief.get("schema_version"), "snapshot_sha256": _sha(brief),
            "qualified_periods": sorted(str(x) for x in (identity.get("periods") or []) if x is not None),
            "ticker": brief.get("ticker")}


def _brief_errors(brief: Mapping[str, Any]) -> list[str]:
    if not brief:
        return ["brief_missing"]
    errors = [f"brief_{key}_incompatible" for key, expected in _SEMANTIC_FLAGS.items() if brief.get(key) != expected]
    if not isinstance(brief.get("ticker"), str) or not brief.get("ticker"):
        errors.append("brief_ticker_missing")
    return errors


def _fact_key(fact: Mapping[str, Any]) -> tuple[str, ...] | None:
    values = tuple(str(fact.get(key)) for key in _FACT_IDENTITY)
    return values if all(fact.get(key) is not None for key in _FACT_IDENTITY) else None


def _fact_provenance_ok(fact: Mapping[str, Any]) -> bool:
    return bool(fact.get("source") or fact.get("evidence_id") or fact.get("citation_id") or fact.get("observation_ids"))


def _facts(brief: Mapping[str, Any]) -> tuple[dict[tuple[str, ...], Mapping[str, Any]], list[str]]:
    out: dict[tuple[str, ...], Mapping[str, Any]] = {}
    errors: list[str] = []
    for raw in brief.get("qualified_facts") or []:
        fact = _m(raw)
        key = _fact_key(fact)
        if key is None or not _fact_provenance_ok(fact):
            errors.append("qualified_fact_semantic_identity_or_provenance_missing")
        elif key in out:
            errors.append("ambiguous_qualified_fact_identity")
        else:
            out[key] = fact
    return out, sorted(set(errors))


def _comparison_state(previous: Mapping[str, Any], current: Mapping[str, Any]) -> tuple[str, list[str]]:
    previous_errors, current_errors = _brief_errors(previous), _brief_errors(current)
    if previous_errors or current_errors:
        return "blocked", sorted({f"previous_{x}" for x in previous_errors} | {f"current_{x}" for x in current_errors})
    if previous.get("ticker") != current.get("ticker"):
        return "incomparable", ["ticker_mismatch"]
    if previous.get("entity_type") != current.get("entity_type"):
        return "incomparable", ["entity_archetype_mismatch"]
    previous_facts, previous_fact_errors = _facts(previous)
    current_facts, current_fact_errors = _facts(current)
    del previous_facts, current_facts
    errors = previous_fact_errors + current_fact_errors
    if "ambiguous_qualified_fact_identity" in errors:
        return "blocked", ["ambiguous_qualified_fact_identity"]
    return ("partially_comparable", sorted(set(errors))) if errors else ("comparable", [])


def _fact_changes(previous: Mapping[str, Any], current: Mapping[str, Any]) -> list[dict[str, Any]]:
    before, before_errors = _facts(previous)
    after, after_errors = _facts(current)
    changes: list[dict[str, Any]] = []
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        if old is None:
            kind = "added"
        elif new is None:
            kind = "removed"
        elif old.get("value") is None and new.get("value") is not None:
            kind = "became_available"
        elif old.get("value") is not None and new.get("value") is None:
            kind = "became_unavailable"
        elif old.get("value") != new.get("value"):
            kind = "changed"
        else:
            kind = "unchanged"
        changes.append({"semantic_identity": dict(zip(_FACT_IDENTITY, key)), "status": kind,
                        "previous": deepcopy(dict(old)) if old is not None else None,
                        "current": deepcopy(dict(new)) if new is not None else None})
    if before_errors or after_errors:
        changes.append({"status": "not_comparable", "reason_codes": sorted(set(before_errors + after_errors))})
    return changes


def _quality_changes(previous: Mapping[str, Any], current: Mapping[str, Any]) -> list[dict[str, Any]]:
    before, after = _m(previous.get("quality")), _m(current.get("quality"))
    changes: list[dict[str, Any]] = []
    for name in sorted(set(before) | set(after)):
        old, new = _m(before.get(name)), _m(after.get(name))
        old_status, new_status = old.get("status"), new.get("status")
        if not old:
            status, direction = "became_available" if new_status == "available" else "added", "not_comparable"
        elif not new:
            status, direction = "became_unavailable" if old_status == "available" else "removed", "not_comparable"
        elif old_status != new_status:
            status, direction = "status_changed", _QUALITY_DIRECTION.get((old_status, new_status), "not_comparable")
        elif _stable(old.get("supporting_facts")) != _stable(new.get("supporting_facts")) or _stable(old.get("warnings")) != _stable(new.get("warnings")):
            status, direction = "supporting_evidence_changed", "not_comparable"
        else:
            status, direction = "unchanged", "unchanged"
        changes.append({"dimension": name, "status": status, "direction": direction,
                        "previous_status": old_status, "current_status": new_status,
                        "previous": deepcopy(dict(old)) if old else None, "current": deepcopy(dict(new)) if new else None})
    return changes


def _risk_map(brief: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {str(item.get("risk_id")): item for item in (_m(brief.get("risks")).get("phase_4b") or [])
            if isinstance(item, Mapping) and item.get("risk_id")}


def _evidence_unavailable(brief: Mapping[str, Any]) -> bool:
    return bool(_m(brief.get("historical_conclusion")).get("missing_evidence") or brief.get("missing_evidence"))


def _risk_changes(previous: Mapping[str, Any], current: Mapping[str, Any]) -> list[dict[str, Any]]:
    before, after = _risk_map(previous), _risk_map(current)
    changes: list[dict[str, Any]] = []
    for risk_id in sorted(set(before) | set(after)):
        old, new = before.get(risk_id), after.get(risk_id)
        if old is None:
            status = "newly_identified"
        elif new is None and _evidence_unavailable(current):
            status = "no_longer_supported_due_to_unavailable_evidence"
        elif new is None:
            status = "no_longer_supported"
        elif _stable(old) != _stable(new):
            status = "supporting_evidence_changed"
        else:
            status = "persistent"
        changes.append({"risk_id": risk_id, "status": status, "previous": deepcopy(dict(old)) if old else None,
                        "current": deepcopy(dict(new)) if new else None})
    return changes


def _catalyst_changes(previous: Mapping[str, Any], current: Mapping[str, Any]) -> list[dict[str, Any]]:
    def indexed(brief: Mapping[str, Any]) -> dict[str, Any]:
        return {str(item.get("condition") or _sha(item)): item for item in (brief.get("catalysts") or []) if isinstance(item, Mapping)}
    before, after = indexed(previous), indexed(current)
    out: list[dict[str, Any]] = []
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        status = "newly_supported" if old is None and _m(new).get("status") == "available" else "added" if old is None else "no_longer_supported" if new is None else "evidence_changed" if _stable(old) != _stable(new) else "unchanged"
        out.append({"condition_id": key, "status": status, "previous": deepcopy(old), "current": deepcopy(new)})
    return out


def _eligibility_change(previous: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, Any]:
    old, new = _m(_m(previous.get("identity")).get("eligibility")), _m(_m(current.get("identity")).get("eligibility"))
    return {"status": "changed" if _stable(old) != _stable(new) else "unchanged", "previous": deepcopy(dict(old)), "current": deepcopy(dict(new))}


def _fundamental_risk_change(previous: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, Any]:
    old, new = _m(_m(previous.get("risks")).get("phase_4c")), _m(_m(current.get("risks")).get("phase_4c"))
    return {"status": "changed" if _stable(old) != _stable(new) else "unchanged", "previous": deepcopy(dict(old)), "current": deepcopy(dict(new))}


def _missing_evidence_changes(previous: Mapping[str, Any], current: Mapping[str, Any]) -> list[dict[str, str]]:
    before, after = {str(x) for x in (previous.get("missing_evidence") or [])}, {str(x) for x in (current.get("missing_evidence") or [])}
    return [{"evidence": item, "status": "became_unavailable" if item in after else "became_available"} for item in sorted(before ^ after)]


def _structural_changes(previous: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, Any]:
    fields = ("status", "required_conditions", "key_dependencies", "invalidation_conditions", "missing_evidence", "supporting_facts")
    out: dict[str, Any] = {}
    for name in ("bear", "base", "bull"):
        old, new = _m(_m(previous.get("scenarios")).get(name)), _m(_m(current.get("scenarios")).get(name))
        changed = [field for field in fields if _stable(old.get(field)) != _stable(new.get(field))]
        out[name] = {"status": "changed" if changed else "unchanged", "changed_fields": changed,
                     "previous": {field: deepcopy(old.get(field)) for field in fields},
                     "current": {field: deepcopy(new.get(field)) for field in fields}}
    return out


def _condition_key(condition: Any) -> str:
    if isinstance(condition, Mapping) and (condition.get("condition_id") or condition.get("id")):
        return str(condition.get("condition_id") or condition.get("id"))
    return _sha(condition)


def _trigger(condition: Mapping[str, Any], current: Mapping[str, Any]) -> str:
    rule = _m(condition.get("trigger"))
    metric, operator = rule.get("canonical_metric"), rule.get("operator")
    if not metric or operator not in {"equals", "greater_than", "less_than"} or "value" not in rule:
        return "unavailable"
    matches = [item for item in current.get("qualified_facts") or [] if isinstance(item, Mapping) and item.get("canonical_metric") == metric]
    if len(matches) != 1 or not _fact_provenance_ok(_m(matches[0])) or matches[0].get("value") is None:
        return "unavailable"
    value, threshold = matches[0].get("value"), rule.get("value")
    try:
        triggered = value == threshold if operator == "equals" else value > threshold if operator == "greater_than" else value < threshold
    except TypeError:
        return "unavailable"
    return "triggered" if triggered else "not_triggered"


def _invalidation_changes(previous: Mapping[str, Any], current: Mapping[str, Any]) -> list[dict[str, Any]]:
    before = {_condition_key(x): x for x in (previous.get("invalidation_conditions") or [])}
    after = {_condition_key(x): x for x in (current.get("invalidation_conditions") or [])}
    out: list[dict[str, Any]] = []
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        status = "new_condition" if old is None else "condition_removed" if new is None else "condition_changed" if _stable(old) != _stable(new) else "unchanged"
        out.append({"condition_id": key, "status": status, "previous": deepcopy(old), "current": deepcopy(new),
                    "trigger_evaluation": _trigger(_m(new), current) if new is not None else "unavailable"})
    return out


def _boundary_changes(previous: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    before, after = _m(previous.get("portfolio_risk_boundary")), _m(current.get("portfolio_risk_boundary"))
    return {name: {"status": "unchanged" if _stable(before.get(name)) == _stable(after.get(name)) else "changed",
                   "previous": deepcopy(before.get(name)), "current": deepcopy(after.get(name))}
            for name in ("liquidity", "portfolio_context", "allocation")}


def _conclusion(previous: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, Any]:
    old, new = _m(previous.get("historical_conclusion")), _m(current.get("historical_conclusion"))
    return {"changed": old.get("status") != new.get("status"), "previous": deepcopy(dict(old)), "current": deepcopy(dict(new)),
            "reason_references": ["historical_conclusion.status"] if old.get("status") != new.get("status") else []}


def _summary(result: Mapping[str, Any]) -> dict[str, Any]:
    categories: list[tuple[int, str, str]] = []
    if result["comparison_status"] not in {"comparable", "partially_comparable"}:
        return {"material_change_detected": False, "change_categories": [], "highest_priority_changes": [],
                "unchanged_critical_boundaries": [], "newly_introduced_limitations": [], "newly_resolved_limitations": [],
                "conclusion_change": result["historical_conclusion"], "invalidation_status": "unavailable"}
    if result["historical_conclusion"]["changed"]: categories.append((_PRIORITY["conclusion"], "conclusion", "historical_conclusion.status"))
    if result["eligibility_change"]["status"] != "unchanged": categories.append((_PRIORITY["eligibility"], "eligibility", "identity.eligibility"))
    if result["fundamental_risk_change"]["status"] != "unchanged": categories.append((_PRIORITY["fundamental_risk"], "fundamental_risk", "risks.phase_4c"))
    for item in result["invalidation_changes"]:
        if item["status"] != "unchanged" or item["trigger_evaluation"] == "triggered": categories.append((_PRIORITY["invalidation"], "invalidation", item["condition_id"]))
    for item in result["quality_changes"]:
        if item["status"] != "unchanged": categories.append((_PRIORITY["quality"], "quality", item["dimension"]))
    for item in result["risk_changes"]:
        if item["status"] != "persistent": categories.append((_PRIORITY["risk"], "risk", item["risk_id"]))
    for item in result["catalyst_changes"]:
        if item["status"] != "unchanged": categories.append((_PRIORITY["evidence"], "catalyst", item["condition_id"]))
    for name, item in result["scenario_changes"].items():
        if item["status"] != "unchanged": categories.append((_PRIORITY["scenario"], "scenario", name))
    for item in result["fact_changes"]:
        if item["status"] not in {"unchanged", "not_comparable"}: categories.append((_PRIORITY["fact"], "fact", _stable(item["semantic_identity"])))
    unchanged = [name for name, item in result["portfolio_gate_changes"].items() if item["status"] == "unchanged" and _m(item.get("current")).get("status") in {"blocked", "blocked_input", "allocation_blocked"}]
    introduced = [item["dimension"] for item in result["quality_changes"] if item["status"] == "became_unavailable"] + [item["evidence"] for item in result["missing_evidence_changes"] if item["status"] == "became_unavailable"]
    resolved = [item["dimension"] for item in result["quality_changes"] if item["status"] == "became_available"] + [item["evidence"] for item in result["missing_evidence_changes"] if item["status"] == "became_available"]
    ordered = sorted(categories, key=lambda item: (item[0], item[1], item[2]))
    return {"material_change_detected": bool(ordered), "change_categories": sorted({item[1] for item in ordered}),
            "highest_priority_changes": [{"category": item[1], "reference": item[2]} for item in ordered[:8]],
            "unchanged_critical_boundaries": unchanged, "newly_introduced_limitations": introduced,
            "newly_resolved_limitations": resolved, "conclusion_change": result["historical_conclusion"],
            "invalidation_status": "triggered" if any(item["trigger_evaluation"] == "triggered" for item in result["invalidation_changes"]) else "unavailable" if any(item["trigger_evaluation"] == "unavailable" for item in result["invalidation_changes"]) else "not_triggered"}


def compare(previous_brief: Mapping[str, Any] | None, current_brief: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a deterministic, historical-only delta.  Missing semantics never imply a change."""
    previous, current = _m(previous_brief), _m(current_brief)
    status, reasons = _comparison_state(previous, current)
    ticker = current.get("ticker") or previous.get("ticker")
    result: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "engine_version": ENGINE_VERSION, "ticker": ticker,
        "analysis_mode": "historical_only_qualified_data", "historical_only": True, "is_actionable": False,
        "previous_snapshot": _snapshot(previous), "current_snapshot": _snapshot(current), "comparison_status": status,
        "previous_qualified_periods": (_snapshot(previous) or {}).get("qualified_periods", []), "current_qualified_periods": (_snapshot(current) or {}).get("qualified_periods", []),
        "comparison_reason_codes": reasons, "fact_changes": [], "quality_changes": [], "risk_changes": [], "scenario_changes": {},
        "invalidation_changes": [], "historical_conclusion": {"changed": False, "previous": None, "current": None, "reason_references": []},
        "portfolio_gate_changes": {}, "catalyst_changes": [], "eligibility_change": {"status": "unavailable", "previous": {}, "current": {}},
        "fundamental_risk_change": {"status": "unavailable", "previous": {}, "current": {}}, "missing_evidence_changes": []}
    if status in {"comparable", "partially_comparable"}:
        result.update({"fact_changes": _fact_changes(previous, current), "quality_changes": _quality_changes(previous, current),
                       "risk_changes": _risk_changes(previous, current), "scenario_changes": _structural_changes(previous, current),
                       "invalidation_changes": _invalidation_changes(previous, current), "historical_conclusion": _conclusion(previous, current),
                       "portfolio_gate_changes": _boundary_changes(previous, current), "catalyst_changes": _catalyst_changes(previous, current),
                       "eligibility_change": _eligibility_change(previous, current), "fundamental_risk_change": _fundamental_risk_change(previous, current)})
        result["missing_evidence_changes"] = _missing_evidence_changes(previous, current)
    result["material_change_summary"] = _summary(result)
    return result


def attach(bundle_entries: dict[str, dict], previous_bundle: Mapping[str, Any] | None, include: bool) -> dict[str, dict]:
    """Attach deltas only when explicitly requested with a caller-selected prior bundle."""
    if not include:
        return bundle_entries
    prior_tickers = _m(previous_bundle).get("tickers")
    prior_tickers = _m(prior_tickers)
    for ticker in sorted(_PILOT_TICKERS):
        entry = bundle_entries.get(ticker)
        if isinstance(entry, dict):
            previous = _m(prior_tickers.get(ticker)).get("qualified_research_brief")
            entry["qualified_research_delta"] = compare(previous, entry.get("qualified_research_brief"))
    return bundle_entries
