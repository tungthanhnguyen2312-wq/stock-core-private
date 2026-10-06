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
            "warnings": _warnings(record),
            "supportive_features_present": _supportive(record),
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
        "false_negative_candidates": 0,
        "features_known": 0,
        "labels": {},
    }


def _add(bucket: dict[str, Any], row: Mapping[str, Any], *, live_sessions: tuple[str, ...]) -> None:
    bucket["rows"] += 1
    session = row.get("session")
    if isinstance(session, str):
        bucket["sessions"].add(session)
    status = row.get("status")
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
        "regimes": sorted(bucket["regimes"]),
        "automatic_threshold_change": False,
        "probability": None,
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
    for row in rows:
        if row.get("population") not in POPULATIONS:
            unclassified += 1
            continue
        populations_seen.add(row["population"])
        refused_t60 += len(row.get("refused_horizons") or [])
        key = (row["population"], row.get("source_type"), row.get("tactical_state"), row.get("posture"), row.get("horizon"))
        bucket = buckets.setdefault(key, _empty_bucket())
        _add(bucket, row, live_sessions=live_sessions)
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
        else:
            cohort["matched_control"] = _edge(cohort, control)
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
    }
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
