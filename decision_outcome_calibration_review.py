"""Outcome, calibration, and false-negative review.

Populations stay separate. The review describes retained evidence. It does not
emit probabilities, target prices, or replacement production thresholds, and it
does not treat horizon 60 as a forward-feedback result.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

CONTRACT_VERSION = "decision_outcome_calibration_review/v1"
IMPLEMENTED_HORIZONS = (1, 3, 5, 10, 20)
HORIZON_FIELDS = {f"forward_close_return_{n}": n for n in IMPLEMENTED_HORIZONS}
EXCURSION_FIELDS = {5: "close_excursion_5", 10: "close_excursion_10", 20: "close_excursion_20"}
MATURE = "MATURE"
PROSPECTIVE_GENUINE = "PROSPECTIVE_GENUINE"
PIT_AUTHORITATIVE = "PIT_AUTHORITATIVE"
RECONSTRUCTED_RESEARCH = "RECONSTRUCTED_RESEARCH"
EXPLANATORY_ONLY = "EXPLANATORY_ONLY"
POPULATIONS = (PROSPECTIVE_GENUINE, PIT_AUTHORITATIVE, RECONSTRUCTED_RESEARCH, EXPLANATORY_ONLY)
SOURCE_TO_POPULATION = {
    "IMMUTABLE_INTEGRATED_T0": PROSPECTIVE_GENUINE,
    "QUALIFIED_LEGACY_INTEGRATED_T0": PROSPECTIVE_GENUINE,
}
TIER_TO_POPULATION = {
    PIT_AUTHORITATIVE: PIT_AUTHORITATIVE,
    RECONSTRUCTED_RESEARCH: RECONSTRUCTED_RESEARCH,
    EXPLANATORY_ONLY: EXPLANATORY_ONLY,
}
CONTROL_POSTURES = frozenset({"WAIT", "AVOID", "INSUFFICIENT_CURRENT_RESEARCH"})
LIVE_DECISION_SESSIONS = ("2026-10-05", "2026-10-06")
INSUFFICIENT = "INSUFFICIENT"
EARLY_DESCRIPTIVE = "EARLY_DESCRIPTIVE"
RESEARCH_USABLE = "RESEARCH_USABLE"
CALIBRATION_CANDIDATE = "CALIBRATION_CANDIDATE"
UNQUALIFIED_SAMPLE = "UNQUALIFIED_SAMPLE"


def sample_quality(mature_count: int, distinct_sessions: int) -> str:
    """Research-sample label. A large sample does not become authority."""
    if mature_count >= 300 and distinct_sessions >= 8:
        return CALIBRATION_CANDIDATE
    if mature_count >= 100 and distinct_sessions >= 5:
        return RESEARCH_USABLE
    if mature_count >= 30 and distinct_sessions >= 3:
        return EARLY_DESCRIPTIVE
    return INSUFFICIENT


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * q)))
    return ordered[index]


def _population(record: Mapping[str, Any]) -> tuple[str | None, str]:
    tier = record.get("semantic_tier")
    source = record.get("source_type")
    tier_population = TIER_TO_POPULATION.get(tier) if isinstance(tier, str) else None
    source_population = SOURCE_TO_POPULATION.get(source) if isinstance(source, str) else None
    if tier_population and source_population and tier_population != source_population:
        return None, "POPULATION_CONFLICT"
    if tier_population:
        return tier_population, "SEMANTIC_TIER"
    if source_population:
        return source_population, "SOURCE_TYPE"
    return None, "POPULATION_UNCLASSIFIED"


def _regime(record: Mapping[str, Any]) -> str | None:
    market = record.get("market_sector_state")
    if isinstance(market, str) and market.strip():
        return market.strip()
    if isinstance(market, Mapping):
        for key in ("market_regime", "breadth_descriptor", "state"):
            value = market.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


NOT_RETAINED_AT_T0 = "FIELD_NOT_RETAINED_AT_T0"
AUTHORITY_DISCLAIMER_WARNINGS = frozenset({
    "TRIGGER_IS_RESEARCH_MEASUREMENT_NOT_EXECUTION_AUTHORITY",
    "STRUCTURAL_INVALIDATION_LEVEL_NOT_A_STOP_LOSS",
})
SUPPORTIVE_AXIS_STATES = frozenset({"CONFIRMED", "ELIGIBLE"})
ADVERSE_AXIS_STATES = frozenset({
    "DISTRIBUTION_RISK", "CONTRADICTED", "INSUFFICIENT", "ABSENT", "UNAVAILABLE",
    "NOT_ELIGIBLE", "INSUFFICIENT_EVIDENCE",
})
FAILURE_LABELS = frozenset({"FALSE_REVERSAL", "FAILED_BREAKOUT"})
# Sign of the retained forward return is the existing descriptive category.
# It is not a new production or policy threshold.
DESCRIPTIVE_ADVERSE = "NEGATIVE_SIGN_OF_RETAINED_FORWARD_RETURN_OR_RETAINED_FAILURE_LABEL"
DESCRIPTIVE_FAVORABLE = "POSITIVE_SIGN_OF_RETAINED_FORWARD_RETURN"


def _warnings(record: Mapping[str, Any]) -> list[str] | None:
    raw = record.get("t0_warnings")
    if raw is None:
        diagnostics = record.get("feedback_diagnostics")
        raw = diagnostics.get("warnings") if isinstance(diagnostics, Mapping) else None
    if raw is None:
        return None
    if not isinstance(raw, list):
        return None
    return [item for item in raw if isinstance(item, str)]


def _axis_state(value: Any) -> str | None:
    if isinstance(value, str) and value and value != NOT_RETAINED_AT_T0:
        return value
    if isinstance(value, Mapping):
        state = value.get("state")
        if isinstance(state, str) and state and state != NOT_RETAINED_AT_T0:
            return state
    return None


def project_explanatory_axes(record: Mapping[str, Any]) -> dict[str, Any]:
    """Read compact axes already retained on the feedback record.

    The calibration review previously looked only for ``t0_warnings`` and
    boolean axis flags. Retained feedback keeps nested ``evidence_axes`` and
    authority-disclaimer strings on trigger and invalidation. This projection
    does not invent a code that is absent, and it does not treat an authority
    disclaimer as a setup warning.
    """
    axes = record.get("evidence_axes") if isinstance(record.get("evidence_axes"), Mapping) else {}
    raw_states = axes.get("axis_states") if isinstance(axes.get("axis_states"), Mapping) else {}
    retained = axes.get("status") == "RETAINED" and bool(raw_states)
    axis_states: dict[str, str] = {}
    supportive: list[str] = []
    adverse: list[str] = []
    if retained:
        for name in sorted(raw_states):
            state = _axis_state(raw_states[name])
            if not state:
                continue
            axis_states[str(name)] = state
            if state in SUPPORTIVE_AXIS_STATES:
                supportive.append(str(name))
            if state in ADVERSE_AXIS_STATES:
                adverse.append(str(name))
    disclaimers: list[str] = []
    for source_name in ("trigger", "invalidation"):
        body = record.get(source_name)
        if not isinstance(body, Mapping):
            continue
        warning = body.get("warning")
        if isinstance(warning, str) and warning in AUTHORITY_DISCLAIMER_WARNINGS:
            disclaimers.append(warning)
    listed = _warnings(record) or []
    setup_codes = sorted({*adverse, *(code for code in listed if code not in AUTHORITY_DISCLAIMER_WARNINGS)})
    trigger = record.get("trigger") if isinstance(record.get("trigger"), Mapping) else {}
    taxonomy = record.get("feedback_taxonomy") if isinstance(record.get("feedback_taxonomy"), Mapping) else {}
    trigger_state = trigger.get("trigger_state")
    confirmation = taxonomy.get("confirmation_status")
    if not retained and not setup_codes:
        retention = "FEATURES_NOT_RETAINED_AT_T0"
        warnings = None
        supportive_present = None
    else:
        retention = "RETAINED" if retained else "SETUP_CODES_ONLY"
        warnings = setup_codes
        supportive_present = bool(supportive) if retained else None
    return {
        "retention": retention,
        "warning_codes": warnings,
        "authority_disclaimer_codes": sorted(set(disclaimers)),
        "supportive_feature_families": supportive if retained else [],
        "adverse_feature_families": adverse if retained else [],
        "axis_states": axis_states,
        "tactical_setup": axis_states.get("TACTICAL_STRUCTURE"),
        "market_regime": _regime(record),
        "sector_context": axis_states.get("MARKET_SECTOR"),
        "confirmation_state": confirmation if isinstance(confirmation, str) else None,
        "trigger_state": trigger_state if isinstance(trigger_state, str) and trigger_state != NOT_RETAINED_AT_T0 else None,
        "supportive_features_present": supportive_present,
    }


def _supportive(record: Mapping[str, Any]) -> bool | None:
    if "supportive_features_present" in record and isinstance(record.get("supportive_features_present"), bool):
        return record["supportive_features_present"]
    axes = record.get("evidence_axes")
    if not isinstance(axes, Mapping):
        return None
    states = axes.get("axis_states")
    if not isinstance(states, Mapping) or not states:
        return None
    flags = [value for value in states.values() if isinstance(value, bool)]
    if not flags:
        return None
    return any(flags)


def compact_horizons(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Project one retained feedback row into per-horizon review rows.

    Horizon 60 is ignored. Missing population drops the row from metrics.
    """
    population, population_reason = _population(record)
    explanatory = project_explanatory_axes(record)
    outcomes = record.get("forward_outcomes") if isinstance(record.get("forward_outcomes"), Mapping) else {}
    horizons = outcomes.get("horizons") if isinstance(outcomes.get("horizons"), Mapping) else {}
    excursions = outcomes.get("close_path_by_horizon") if isinstance(outcomes.get("close_path_by_horizon"), Mapping) else {}
    taxonomy = record.get("feedback_taxonomy") if isinstance(record.get("feedback_taxonomy"), Mapping) else {}
    projected = []
    refused = [name for name in horizons if name not in HORIZON_FIELDS and ("60" in name or name == "T60")]
    for name, horizon in HORIZON_FIELDS.items():
        body = horizons.get(name)
        if not isinstance(body, Mapping):
            continue
        excursion_name = EXCURSION_FIELDS.get(horizon)
        excursion = excursions.get(excursion_name) if excursion_name else None
        excursion = excursion if isinstance(excursion, Mapping) else {}
        projected.append({
            "population": population,
            "population_reason": population_reason,
            "source_type": record.get("source_type") or "UNSPECIFIED",
            "session": record.get("decision_session"),
            "ticker": record.get("ticker"),
            "posture": record.get("research_action_posture") or "UNSPECIFIED",
            "tactical_state": record.get("tactical_structure_state") or "UNSPECIFIED",
            "regime": _regime(record),
            "horizon": horizon,
            "status": body.get("status"),
            "forward_return": body.get("return") if isinstance(body.get("return"), (int, float)) else None,
            "mfe": excursion.get("CLOSE_MFE") if isinstance(excursion.get("CLOSE_MFE"), (int, float)) else None,
            "mae": excursion.get("CLOSE_MAE") if isinstance(excursion.get("CLOSE_MAE"), (int, float)) else None,
            "outcome_label": taxonomy.get("label"),
            "warnings": explanatory["warning_codes"] if explanatory["warning_codes"] is not None else _warnings(record),
            "supportive_features_present": explanatory["supportive_features_present"] if explanatory["supportive_features_present"] is not None else _supportive(record),
            "explanatory_axes": explanatory,
            "price_basis": body.get("status") if body.get("status") == "PRICE_BASIS_INCOMPATIBLE" else None,
            "refused_horizons": refused,
        })
    return projected


def _empty_bucket() -> dict[str, Any]:
    return {
        "rows": 0,
        "mature": 0,
        "pending": 0,
        "sessions": set(),
        "mature_sessions": set(),
        "returns": [],
        "mfe": [],
        "mae": [],
        "regimes": set(),
        "negative_mature": 0,
        "negative_with_warnings": 0,
        "warnings_known": 0,
        "warning_rows": 0,
        "false_negative_candidates": 0,
        "features_known": 0,
        "price_basis_incompatible_rows": 0,
        "labels": {},
    }


def _add(bucket: dict[str, Any], row: Mapping[str, Any], *, live_sessions: tuple[str, ...]) -> None:
    bucket["rows"] += 1
    session = row.get("session")
    if isinstance(session, str):
        bucket["sessions"].add(session)
    status = row.get("status")
    if row.get("price_basis") == "PRICE_BASIS_INCOMPATIBLE" or status == "PRICE_BASIS_INCOMPATIBLE":
        bucket["price_basis_incompatible_rows"] += 1
    live = isinstance(session, str) and session in live_sessions and status != MATURE
    if live:
        bucket["pending"] += 1
        return
    if status != MATURE:
        return
    bucket["mature"] += 1
    if isinstance(session, str):
        bucket["mature_sessions"].add(session)
    regime = row.get("regime")
    if isinstance(regime, str):
        bucket["regimes"].add(regime)
    value = row.get("forward_return")
    if isinstance(value, (int, float)):
        bucket["returns"].append(float(value))
        if value < 0:
            bucket["negative_mature"] += 1
            warnings = row.get("warnings")
            if isinstance(warnings, list):
                bucket["warnings_known"] += 1
                if warnings:
                    bucket["negative_with_warnings"] += 1
    if isinstance(row.get("mfe"), (int, float)):
        bucket["mfe"].append(float(row["mfe"]))
    if isinstance(row.get("mae"), (int, float)):
        bucket["mae"].append(float(row["mae"]))
    label = row.get("outcome_label")
    if isinstance(label, str):
        bucket["labels"][label] = bucket["labels"].get(label, 0) + 1
    supportive = row.get("supportive_features_present")
    if isinstance(supportive, bool):
        bucket["features_known"] += 1
        if supportive and row.get("posture") in CONTROL_POSTURES:
            bucket["false_negative_candidates"] += 1
    if isinstance(row.get("warnings"), list):
        bucket["warning_rows"] += 1


def _distribution(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"status": "MISSING", "n": 0}
    return {
        "status": "PRESENT",
        "n": len(values),
        "median": _median(values),
        "p25": _quantile(values, 0.25),
        "p50": _quantile(values, 0.50),
        "p75": _quantile(values, 0.75),
    }


def _labeled_rate(bucket: dict[str, Any], label: str) -> dict[str, Any]:
    count = bucket["labels"].get(label, 0)
    if count == 0:
        return {"status": "LABEL_NOT_RETAINED", "rate": None}
    if bucket["mature"] <= 0:
        return {"status": "LABEL_NOT_RETAINED", "rate": None}
    return {"status": "PRESENT", "count": count, "rate": count / bucket["mature"]}


def _view(key: tuple[Any, ...], bucket: dict[str, Any]) -> dict[str, Any]:
    population, source_type, tactical_state, posture, horizon = key
    quality = sample_quality(bucket["mature"], len(bucket["mature_sessions"]))
    warnings_status = "PRESENT" if bucket["warnings_known"] else "WARNINGS_NOT_RETAINED"
    feature_status = "PRESENT" if bucket["features_known"] else "FEATURES_NOT_RETAINED"
    return {
        "population": population,
        "source_type": source_type,
        "tactical_state": tactical_state,
        "posture": posture,
        "horizon": horizon,
        "row_count": bucket["rows"],
        "mature_count": bucket["mature"],
        "pending_live_count": bucket["pending"],
        "distinct_mature_sessions": sorted(bucket["mature_sessions"]),
        "sample_quality": quality,
        "forward_return": _distribution(bucket["returns"]),
        "mfe": _distribution(bucket["mfe"]),
        "mae": _distribution(bucket["mae"]),
        "maximum_drawdown": {"status": "MISSING"},
        "false_reversal_rate": _labeled_rate(bucket, "FALSE_REVERSAL"),
        "failed_breakout_rate": _labeled_rate(bucket, "FAILED_BREAKOUT"),
        "outcome_labels": dict(sorted(bucket["labels"].items())),
        "false_positive_review": {
            "negative_mature_count": bucket["negative_mature"],
            "negative_with_retained_warnings": bucket["negative_with_warnings"],
            "status": warnings_status,
        },
        "false_negative_review": {
            "supportive_features_while_wait_or_avoid": bucket["false_negative_candidates"],
            "status": feature_status,
        },
        "warning_rows": bucket["warning_rows"],
        "features_known": bucket["features_known"],
        "price_basis_incompatible_rows": bucket["price_basis_incompatible_rows"],
        "regimes": sorted(bucket["regimes"]),
        "automatic_threshold_change": False,
        "probability": None,
    }


def classify_explanation(row: Mapping[str, Any]) -> str | None:
    """Describe a mature case without introducing a return threshold.

    Adverse means a retained failure label or a negative retained forward
    return. Favorable means a positive retained forward return. Those signs
    are descriptive categories already used by the review.
    """
    if row.get("status") != MATURE:
        return None
    value = row.get("forward_return")
    label = row.get("outcome_label")
    adverse = (isinstance(value, (int, float)) and not isinstance(value, bool) and value < 0) or label in FAILURE_LABELS
    favorable = isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0
    posture = row.get("posture")
    if posture not in CONTROL_POSTURES and adverse:
        if isinstance(row.get("warnings"), list):
            return "FALSE_POSITIVE_EXPLAINABLE"
        return "FALSE_POSITIVE_FEATURES_NOT_RETAINED"
    if posture in CONTROL_POSTURES and favorable:
        if row.get("supportive_features_present") is True:
            return "FALSE_NEGATIVE_EXPLAINABLE"
        if row.get("supportive_features_present") is None:
            return "FALSE_NEGATIVE_FEATURES_NOT_RETAINED"
    return None


def control_readiness(setup: Mapping[str, Any], control: Mapping[str, Any] | None) -> dict[str, Any]:
    """Gates for a matched-control edge. A failing gate does not yield a number."""
    if setup.get("posture") in CONTROL_POSTURES:
        return {"state": "SETUP_NOT_ELIGIBLE", "edge": None, "control_pool_size": 0}
    if int(setup.get("mature_count") or 0) <= 0:
        return {"state": "OUTCOME_NOT_MATURE", "edge": None, "control_pool_size": 0}
    if int(setup.get("warning_rows") or 0) == 0 and int(setup.get("features_known") or 0) == 0:
        return {"state": "FEATURES_NOT_RETAINED", "edge": None, "control_pool_size": 0}
    if not setup.get("regimes"):
        return {"state": "REGIME_DIMENSION_MISSING", "edge": None, "control_pool_size": 0}
    if int(setup.get("price_basis_incompatible_rows") or 0) > 0:
        return {"state": "PRICE_BASIS_INCOMPATIBLE", "edge": None, "control_pool_size": 0}
    pool = int(control.get("mature_count") or 0) if control else 0
    if control is None or pool <= 0:
        return {"state": "INSUFFICIENT_CONTROL_POOL", "edge": None, "control_pool_size": pool}
    usable = {RESEARCH_USABLE, CALIBRATION_CANDIDATE}
    if setup.get("sample_quality") not in usable or control.get("sample_quality") not in usable:
        return {"state": "UNQUALIFIED_SAMPLE", "edge": None, "control_pool_size": pool}
    if int(control.get("warning_rows") or 0) == 0 and int(control.get("features_known") or 0) == 0:
        return {"state": "FEATURES_NOT_RETAINED", "edge": None, "control_pool_size": pool}
    if control.get("regimes") != setup.get("regimes"):
        return {"state": "REGIME_DIMENSION_MISSING", "edge": None, "control_pool_size": pool}
    setup_median = (setup.get("forward_return") or {}).get("median")
    control_median = (control.get("forward_return") or {}).get("median")
    if setup_median is None or control_median is None:
        return {"state": "UNQUALIFIED_SAMPLE", "edge": None, "control_pool_size": pool}
    return {
        "state": "CONTROL_READY",
        "edge": setup_median - control_median,
        "control_pool_size": pool,
        "matching_dimensions": ["population", "source_type", "horizon", "regime"],
        "automatic_threshold_change": False,
    }


def _edge(setup: Mapping[str, Any], control: Mapping[str, Any] | None) -> dict[str, Any]:
    if setup.get("posture") in CONTROL_POSTURES:
        return {"status": "NOT_A_SETUP_COHORT", "edge": None}
    if control is None:
        return {"status": UNQUALIFIED_SAMPLE, "edge": None, "reason": "NO_MATCHED_CONTROL"}
    usable = {RESEARCH_USABLE, CALIBRATION_CANDIDATE}
    if setup.get("sample_quality") not in usable or control.get("sample_quality") not in usable:
        return {"status": UNQUALIFIED_SAMPLE, "edge": None, "reason": "SAMPLE_QUALITY"}
    setup_regimes = setup.get("regimes") or []
    control_regimes = control.get("regimes") or []
    if len(setup_regimes) != 1 or setup_regimes != control_regimes:
        return {"status": UNQUALIFIED_SAMPLE, "edge": None, "reason": "REGIME_MATCH"}
    setup_median = (setup.get("forward_return") or {}).get("median")
    control_median = (control.get("forward_return") or {}).get("median")
    if setup_median is None or control_median is None:
        return {"status": UNQUALIFIED_SAMPLE, "edge": None, "reason": "RETURN_MISSING"}
    return {
        "status": "COMPUTED",
        "edge": setup_median - control_median,
        "control_postures": CONTROL_POSTURES,
        "regime": setup_regimes[0],
    }


def review_observations(rows: Iterable[Mapping[str, Any]], *, live_sessions: tuple[str, ...] = LIVE_DECISION_SESSIONS) -> dict[str, Any]:
    buckets: dict[tuple[Any, ...], dict[str, Any]] = {}
    unclassified = 0
    refused_t60 = 0
    populations_seen: set[str] = set()
    explanation_counts: dict[str, int] = {}
    earliest_retained_feature_session: str | None = None
    for row in rows:
        if row.get("population") not in POPULATIONS:
            unclassified += 1
            continue
        populations_seen.add(row["population"])
        refused_t60 += len(row.get("refused_horizons") or [])
        key = (row["population"], row.get("source_type"), row.get("tactical_state"), row.get("posture"), row.get("horizon"))
        bucket = buckets.setdefault(key, _empty_bucket())
        _add(bucket, row, live_sessions=live_sessions)
        session = row.get("session")
        status = row.get("status")
        live = isinstance(session, str) and session in live_sessions and status != MATURE
        if not live and status == MATURE:
            kind = classify_explanation(row)
            if kind:
                explanation_counts[kind] = explanation_counts.get(kind, 0) + 1
        axes = row.get("explanatory_axes") if isinstance(row.get("explanatory_axes"), Mapping) else {}
        if axes.get("retention") == "RETAINED" and isinstance(session, str):
            if earliest_retained_feature_session is None or session < earliest_retained_feature_session:
                earliest_retained_feature_session = session
    cohorts = [_view(key, bucket) for key, bucket in sorted(buckets.items(), key=lambda item: json.dumps(item[0]))]
    by_match: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for cohort in cohorts:
        match = (cohort["population"], cohort["source_type"], cohort["horizon"])
        by_match.setdefault(match, []).append(cohort)
    for cohort in cohorts:
        siblings = by_match[(cohort["population"], cohort["source_type"], cohort["horizon"])]
        controls = [
            item for item in siblings
            if item["posture"] in CONTROL_POSTURES and item["tactical_state"] != cohort["tactical_state"] and item["regimes"] == cohort["regimes"] and item["regimes"]
        ]
        control = controls[0] if len(controls) == 1 else None
        if len(controls) > 1:
            cohort["matched_control"] = {"status": UNQUALIFIED_SAMPLE, "edge": None, "reason": "AMBIGUOUS_CONTROL"}
            cohort["control_readiness"] = {"state": "INSUFFICIENT_CONTROL_POOL", "edge": None, "reason": "AMBIGUOUS_CONTROL", "control_pool_size": sum(item["mature_count"] for item in controls)}
        else:
            cohort["matched_control"] = _edge(cohort, control)
            cohort["control_readiness"] = control_readiness(cohort, control)
    mature_by_horizon: dict[str, int] = {}
    sessions_by_horizon: dict[str, set[str]] = {}
    for cohort in cohorts:
        name = f"T{cohort['horizon']}"
        mature_by_horizon[name] = mature_by_horizon.get(name, 0) + cohort["mature_count"]
        sessions_by_horizon.setdefault(name, set()).update(cohort["distinct_mature_sessions"])
    pending_rows = sum(bucket["pending"] for bucket in buckets.values())
    body = {
        "contract_version": CONTRACT_VERSION,
        "implemented_horizons": list(IMPLEMENTED_HORIZONS),
        "t60_engine_horizon": False,
        "refused_t60_fields": refused_t60,
        "populations_present": sorted(populations_seen),
        "population_mixing": False,
        "unclassified_rows": unclassified,
        "automatic_threshold_change": False,
        "probability": None,
        "authority_promoted": False,
        "mature_counts": {name: {"rows": mature_by_horizon.get(name, 0), "decision_sessions": sorted(sessions_by_horizon.get(name, set()))} for name in ("T1", "T3", "T5", "T10", "T20")},
        "pending_live_horizon_rows": pending_rows,
        "pending_live_sessions": list(live_sessions),
        "cohorts": cohorts,
        "explanation": {
            "adverse_category": DESCRIPTIVE_ADVERSE,
            "favorable_category": DESCRIPTIVE_FAVORABLE,
            "policy_threshold_introduced": False,
            "counts": dict(sorted(explanation_counts.items())),
            "false_positive_explainable": explanation_counts.get("FALSE_POSITIVE_EXPLAINABLE", 0),
            "false_negative_explainable": explanation_counts.get("FALSE_NEGATIVE_EXPLAINABLE", 0),
        },
        "earliest_retained_feature_session": earliest_retained_feature_session,
    }
    readiness_counts: dict[str, int] = {}
    qualified_edges = 0
    for cohort in cohorts:
        state = cohort["control_readiness"]["state"]
        readiness_counts[state] = readiness_counts.get(state, 0) + 1
        if state == "CONTROL_READY" and cohort["control_readiness"].get("edge") is not None:
            qualified_edges += 1
    body["control_readiness_counts"] = dict(sorted(readiness_counts.items()))
    body["qualified_control_edges"] = qualified_edges
    identity_material = {
        "contract_version": CONTRACT_VERSION,
        "mature_counts": body["mature_counts"],
        "cohorts": [
            {field: cohort[field] for field in ("population", "source_type", "tactical_state", "posture", "horizon", "mature_count", "sample_quality", "matched_control")}
            for cohort in cohorts
        ],
    }
    digest = json.dumps(identity_material, sort_keys=True, separators=(",", ":"), default=str)
    body["review_identity"] = "decision_outcome_calibration_review:" + hashlib.sha256(digest.encode("utf-8")).hexdigest()
    return body


def iter_feedback_records(path: Path):
    """Yield feedback records one at a time. The caller must not retain them."""
    key = b'"feedback_records":'
    decoder = json.JSONDecoder()
    with Path(path).open("rb") as handle:
        prefix = handle.read(400_000)
        index = prefix.find(key)
        if index < 0:
            raise ValueError("FEEDBACK_RECORDS_ABSENT")
        handle.seek(index + len(key))
        buffer = ""
        started = False
        while True:
            chunk = handle.read(1_000_000)
            if chunk:
                buffer += chunk.decode("utf-8")
            if not started:
                buffer = buffer.lstrip()
                if not buffer and chunk:
                    continue
                if not buffer.startswith("["):
                    raise ValueError("FEEDBACK_RECORDS_NOT_AN_ARRAY")
                buffer = buffer[1:]
                started = True
            while True:
                buffer = buffer.lstrip()
                if buffer.startswith(","):
                    buffer = buffer[1:]
                    continue
                if buffer.startswith("]"):
                    return
                if not buffer:
                    break
                try:
                    record, end = decoder.raw_decode(buffer)
                except json.JSONDecodeError:
                    if not chunk:
                        raise
                    break
                yield record
                buffer = buffer[end:]
            if not chunk:
                return


def review_feedback_artifact(path: Path, *, live_sessions: tuple[str, ...] = LIVE_DECISION_SESSIONS) -> dict[str, Any]:
    rows = []
    for record in iter_feedback_records(path):
        rows.extend(compact_horizons(record))
        del record
    review = review_observations(rows, live_sessions=live_sessions)
    review["source_name"] = Path(path).name
    review["storage_footprint"] = {
        "persisted": False,
        "source_policy": "stream_one_feedback_record_then_discard",
        "full_artifact_retained_in_memory": False,
    }
    return review
