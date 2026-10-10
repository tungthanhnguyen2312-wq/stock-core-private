"""current_thesis_case_context/v1: deterministic, evidence-bound ``thesis_cases`` decision input.

``current_valuation_opportunity_integration.build_artifacts`` and ``opportunity_context.
build_ticker_opportunity`` have accepted a ``thesis_cases`` argument since before this module
existed, but the canonical current chain has always passed ``None`` for it (see
``canonical_current_product_projections.materialize_current_investment_decision_workspace``):
the retained scenario contracts (``current_research_scenario_context``, ``current_evidence_
bound_scenario``) were traced by the previous milestone to be presentation/research-condition
artifacts, not this decision-input contract, and no other module built one. This module is that
input, built fresh from evidence two already-upstream, already-governed current-session
contracts independently supply -- never by renaming a presentation artifact, never by inventing
probability, target price, expected return, action, or sizing.

Two of the five ``opportunity_context._downside_axis``/``_catalyst_axis`` fields this contract
can populate are already served by current, upstream, market-wide sources today. Technical
invalidation comes from ``tactical_confirmation_invalidation_boundaries/v1`` (via
``tactical_behavior_context``). Event context instead crosses the version-aware
``current_event_catalyst_classification`` boundary, which emits only qualified current catalysts
and preserves non-catalyst event classifications for lineage. The two fields with no other
current source -- ``fundamental_invalidation`` and ``counter_thesis_evidence`` -- are this
module's other contribution, built from ``financial_analysis_context/v2``'s own categorical
state vocabulary (never its ``positive_evidence``/``negative_evidence``/``conflicting_evidence``
prose lists -- those are presentation text, not structured evidence, and are never read here).
``counter_thesis_evidence`` is a short string-tag list (matching the existing ``key_counter_
thesis``/``counter_thesis`` vocabulary contract every other contributor already uses, never a
structured object) and deliberately excludes profitability/margin/balance-sheet/cash-conversion
readings that ``security_decision_context._financial_analysis_annotation`` already tags from the
exact same record via its own separate ``financial_analysis`` argument -- re-emitting those here
would double-count one observed fact as two list entries. The full structured evidence for every
dimension (duplicated ones included) is preserved separately in ``counter_thesis_evidence_
detail`` for lineage/taxonomy completeness; only genuinely additive dimensions (growth_state,
adverse corporate events) reach the tag list.
A third class, ``risk_evidence`` (genuinely adverse/cancelled/conflicting corporate events), is
additive context not read by any consumer today but preserved for lineage completeness per the
case taxonomy this contract is required to support. It deliberately does NOT trigger on a
retained event merely carrying a non-empty ``warnings`` list -- the real
``current_official_event_context/v1`` corpus stamps a fixed authority-boundary disclaimer into
every single retained event's ``warnings`` (routine CASH_DIVIDEND/AGM events included), which is
boilerplate, not signal; see ``_risk_evidence``'s docstring for the overclassification this
module's first draft caught and fixed before this milestone's checkpoint.

Both source families -- ``financial_analysis_product_context`` and corporate event context --
are the exact same upstream artifacts ``opportunity_context.build_ticker_opportunity`` already
accepts as independent arguments; this module never reads security_decision_context, Investment
Decision Workspace, Screener, or portfolio output, so it cannot create a decision-input cycle.

Zero silent drops: every ticker in the caller-supplied ``daily_tickers`` set receives a record,
even when neither source covers it (record present, every evidence list empty, ``fundamental_
invalidation`` explicitly ``UNAVAILABLE``). The Daily ticker denominator is never widened or
narrowed by this module.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from typing import Any, Mapping

from current_event_catalyst_classification import (
    METHOD_VERSION as CATALYST_METHOD_VERSION,
    NEGATIVE_CATALYST,
    POSITIVE_CATALYST,
    classify_events,
)

CONTRACT_VERSION = "current_thesis_case_context/v1"
MILESTONE = "CANONICAL_EVIDENCE_BOUND_THESIS_CASES_DECISION_INPUT_V1"
SCHEMA_VERSION = "1.0.0"

#: (financial_analysis_context/v2 state key, positive value, negative value, thesis dimension).
#: Order is the deterministic priority used to pick the single fundamental_invalidation boundary
#: when more than one dimension is currently positive -- never more than one boundary per ticker.
FA_V2_STATE_DIMENSIONS: tuple[tuple[str, str, str, str], ...] = (
    ("profitability_state", "PROFITABLE", "LOSS_MAKING", "PROFITABILITY"),
    ("margin_state", "MARGIN_EXPANDING", "MARGIN_COMPRESSING", "MARGIN"),
    ("balance_sheet_state", "STRENGTHENING", "DETERIORATING", "BALANCE_SHEET"),
    ("cash_conversion_state", "HEALTHY", "WEAK", "CASH_CONVERSION"),
)
#: States with a qualified negative reading but no paired positive counterpart in the same V2
#: vocabulary -- counter-thesis evidence only, never an invalidation boundary baseline.
FA_V2_NEGATIVE_ONLY_STATES: tuple[tuple[str, str, str], ...] = (
    ("growth_state", "CONTRACTING", "GROWTH"),
)
METHOD_INVALIDATION = "FA_V2_POSITIVE_STATE_REVERSAL_BOUNDARY/v1"
METHOD_EVIDENCE = "financial_analysis_context/v2 categorical state vocabulary"
METHOD_RISK = "current_event_catalyst_classification/v1 adverse event scan"
_IDENTITY_EXCLUDED = {"artifact_sha256", "artifact_identity", "requested_at"}


class ThesisCaseContextError(ValueError):
    """A required invariant of this contract is violated."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(value: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in value.items() if key not in _IDENTITY_EXCLUDED}
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"{CONTRACT_VERSION}:{digest}"}


def _evidence(*, case_class: str, source_dimension: str, metric_or_state: str, value: Any,
              as_of: str | None, method: str, evidence_tier: str, reason: str,
              source_identity: str | None = None) -> dict[str, Any]:
    return {
        "case_class": case_class, "source_dimension": source_dimension, "metric_or_state": metric_or_state,
        "value": value, "as_of": as_of, "method": method, "evidence_tier": evidence_tier,
        "reason": reason, "source_identity": source_identity,
    }


def _fa_record(financial_analysis_product_context: Mapping[str, Any] | None, ticker: str) -> Mapping[str, Any] | None:
    records = (financial_analysis_product_context or {}).get("records") if isinstance(financial_analysis_product_context, Mapping) else None
    record = (records or {}).get(ticker) if isinstance(records, Mapping) else None
    return record if isinstance(record, Mapping) and record.get("status") == "AVAILABLE" else None


#: Dimensions security_decision_context._financial_analysis_annotation already turns into
#: security_decision_context counter-thesis tags (FA_V2_LOSS_MAKING, FA_V2_MARGIN_COMPRESSING,
#: FA_V2_BALANCE_SHEET_DETERIORATING, FA_V2_CASH_CONVERSION_WEAK) from the exact same
#: financial_analysis_product_context record via the SEPARATE ``financial_analysis`` argument
#: opportunity_context.build_ticker_opportunity already accepts. A negative reading on one of
#: these is still recorded here for lineage/taxonomy completeness (``counter_thesis_evidence_
#: detail``, case_classes_present), but never re-emitted as a ``key_counter_thesis`` tag --
#: that would double-count identical evidence under two different pipes.
_DUPLICATE_COVERED_DIMENSIONS = frozenset({"PROFITABILITY", "MARGIN", "BALANCE_SHEET", "CASH_CONVERSION"})


def _supporting_and_counter_evidence(fa_record: Mapping[str, Any] | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Full structured SUPPORT/COUNTER evidence (all dimensions) -- lineage/taxonomy detail, not
    the consumer-facing ``counter_thesis_evidence`` tag list (see ``_counter_thesis_tags``)."""
    if fa_record is None:
        return [], []
    as_of = fa_record.get("as_of_financial_period")
    identity = fa_record.get("lineage_ref")
    supporting: list[dict[str, Any]] = []
    counter: list[dict[str, Any]] = []
    for key, positive, negative, dimension in FA_V2_STATE_DIMENSIONS:
        value = fa_record.get(key)
        if value == positive:
            supporting.append(_evidence(
                case_class="SUPPORT", source_dimension=dimension, metric_or_state=positive, value=key,
                as_of=as_of, method=METHOD_EVIDENCE, evidence_tier="OPERATIONAL_PROXY", source_identity=identity,
                reason=f"financial_analysis_context/v2 reports {key}={positive} for the retained current period.",
            ))
        elif value == negative:
            counter.append(_evidence(
                case_class="COUNTER", source_dimension=dimension, metric_or_state=negative, value=key,
                as_of=as_of, method=METHOD_EVIDENCE, evidence_tier="OPERATIONAL_PROXY", source_identity=identity,
                reason=f"financial_analysis_context/v2 reports {key}={negative} for the retained current period.",
            ))
    for key, negative, dimension in FA_V2_NEGATIVE_ONLY_STATES:
        if fa_record.get(key) == negative:
            counter.append(_evidence(
                case_class="COUNTER", source_dimension=dimension, metric_or_state=negative, value=key,
                as_of=as_of, method=METHOD_EVIDENCE, evidence_tier="OPERATIONAL_PROXY", source_identity=identity,
                reason=f"financial_analysis_context/v2 reports {key}={negative} for the retained current period.",
            ))
    return supporting, counter


def _counter_thesis_tags(counter_detail: list[dict[str, Any]], risk: list[dict[str, Any]]) -> list[str]:
    """The consumer-facing ``counter_thesis_evidence`` tag list -- short string tags, matching
    the existing ``key_counter_thesis``/``counter_thesis`` vocabulary contract every other
    contributor to that field already uses (never a structured object). Excludes any dimension
    ``security_decision_context._financial_analysis_annotation`` already tags from the same
    underlying evidence, so a single observed fact is never counted twice in one list."""
    tags = [
        f"FA_V2_{item['source_dimension']}_{item['metric_or_state']}"
        for item in counter_detail if item["source_dimension"] not in _DUPLICATE_COVERED_DIMENSIONS
    ]
    tags.extend(f"ADVERSE_CORPORATE_EVENT_{item['value']}" for item in risk)
    return tags


def _fundamental_invalidation(fa_record: Mapping[str, Any] | None) -> dict[str, Any]:
    if fa_record is None:
        return {"status": "UNAVAILABLE", "reason": "FA_V2_CONTEXT_ABSENT", "thesis_dimension": None,
                "trigger_type": None, "as_of": None, "method": METHOD_INVALIDATION, "source_identity": None}
    as_of = fa_record.get("as_of_financial_period")
    identity = fa_record.get("lineage_ref")
    for key, positive, negative, dimension in FA_V2_STATE_DIMENSIONS:
        if fa_record.get(key) != positive:
            continue
        if not as_of:
            return {
                "status": "CONDITIONAL", "thesis_dimension": dimension, "trigger_type": f"{dimension}_STATE_REVERSAL",
                "baseline_state": positive, "watch_state": negative, "as_of": None, "method": METHOD_INVALIDATION,
                "source_identity": identity,
                "reason": f"{dimension} is currently {positive} but the retained record carries no financial period identity to anchor the boundary.",
            }
        return {
            "status": "READY", "thesis_dimension": dimension, "trigger_type": f"{dimension}_STATE_REVERSAL",
            "baseline_state": positive, "watch_state": negative,
            "comparison": f"FUTURE_{key.upper()}_EQUALS_{negative}",
            "as_of": as_of, "method": METHOD_INVALIDATION, "source_identity": identity,
            "reason": f"{dimension} is currently {positive}; a future retained {key}={negative} would reverse this fundamental support for the thesis.",
        }
    return {"status": "UNAVAILABLE", "reason": "NO_POSITIVE_FA_V2_STATE_TO_INVALIDATE", "thesis_dimension": None,
            "trigger_type": None, "as_of": as_of, "method": METHOD_INVALIDATION, "source_identity": identity}


def _event_classifications(event_record: Mapping[str, Any] | None, *, event_contract_version: str | None) -> list[dict[str, Any]]:
    events = (event_record or {}).get("events") if isinstance(event_record, Mapping) else None
    return classify_events(events if isinstance(events, list) else [], contract_version=event_contract_version)


def _risk_evidence(classifications: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Adverse-event risk evidence only -- never a general-purpose warnings scan.

    A first version of this function treated ANY non-empty ``event["warnings"]`` as adverse.
    Real retained ``current_official_event_context/v1`` evidence (see
    ``docs/canonical_evidence_bound_thesis_cases_replay_20260913.md``) proved that wrong: every
    single retained event -- routine CASH_DIVIDEND/AGM events included -- carries a fixed,
    templated authority-boundary disclaimer in ``warnings``
    ("No event impact, probability, score, target, or recommendation is derived.", etc.), not a
    signal. That version fabricated RISK evidence on 1,101 of 1,683 tickers from pure boilerplate.
    Only a genuinely adverse event status/state (``event_status`` in the older
    ``current_corporate_event_context`` vocabulary, or ``event_state`` in the real
    ``current_official_event_context/v1`` vocabulary this chain actually supplies) counts. Neither
    real contract's retained corpus currently emits an adverse value here, so RISK legitimately
    stays empty market-wide today -- an honest zero, not a suppressed signal.
    """
    risk: list[dict[str, Any]] = []
    for event in classifications:
        if event.get("catalyst_class") != NEGATIVE_CATALYST:
            continue
        risk.append(_evidence(
            case_class="RISK", source_dimension="CORPORATE_EVENT", metric_or_state=event.get("event_type"),
            value=event.get("event_state"), as_of=event.get("known_at") or event.get("event_date"),
            method=METHOD_RISK, evidence_tier=event.get("fitness") or "UNSPECIFIED",
            source_identity=event.get("source_event_identity"),
            reason=f"Retained corporate event classification is adverse: {event.get('event_state')}.",
        ))
    return risk


def build_ticker_case(*, ticker: str, as_of_session: str, fa_record: Mapping[str, Any] | None,
                       event_record: Mapping[str, Any] | None, event_contract_version: str | None) -> dict[str, Any]:
    supporting, counter_detail = _supporting_and_counter_evidence(fa_record)
    fundamental_invalidation = _fundamental_invalidation(fa_record)
    event_classifications = _event_classifications(event_record, event_contract_version=event_contract_version)
    catalysts = [item for item in event_classifications if item["catalyst_class"] == POSITIVE_CATALYST]
    risk = _risk_evidence(event_classifications)
    counter_tags = _counter_thesis_tags(counter_detail, risk)
    case_classes_present = sorted({
        *(["SUPPORT"] if supporting else []),
        *(["COUNTER"] if counter_detail else []),
        *(["RISK"] if risk else []),
        *(["CATALYST"] if catalysts else []),
        *(["INVALIDATION"] if fundamental_invalidation["status"] != "UNAVAILABLE" else []),
    })
    evidence_gaps = []
    if fa_record is None:
        evidence_gaps.append({"dimension": "FINANCIAL_ANALYSIS_V2", "status": "EVIDENCE_GAP", "reason": "FA_V2_CONTEXT_ABSENT"})
    if not risk and event_record is None:
        evidence_gaps.append({"dimension": "CORPORATE_EVENT", "status": "EVIDENCE_GAP", "reason": "EVENT_CONTEXT_ABSENT_FOR_TICKER"})
    return {
        "ticker": ticker,
        "as_of_session": as_of_session,
        "case_classes_present": case_classes_present,
        "supporting_evidence": supporting,
        # Consumer-facing: opportunity_context._downside_axis reads this verbatim into
        # downside_invalidation.thesis_conflict -> security_decision_context's key_counter_thesis
        # -- a short string-tag list, exactly like every other contributor to that field. The full
        # structured evidence (all dimensions, including ones financial_analysis_context/v2
        # already covers via the separate financial_analysis argument) lives in
        # counter_thesis_evidence_detail instead, so nothing is double-counted in one tag list.
        "counter_thesis_evidence": counter_tags,
        "counter_thesis_evidence_detail": counter_detail,
        "risk_evidence": risk,
        "catalysts": catalysts,
        "retained_event_context": event_classifications,
        "catalyst_axis_reason": "CANONICAL_EVENT_CATALYST_CLASSIFICATION_APPLIED",
        "technical_invalidation": {
            "status": "UNAVAILABLE",
            "reason": "TECHNICAL_INVALIDATION_ALREADY_SOURCED_FROM_TACTICAL_CONFIRMATION_INVALIDATION_BOUNDARIES_VIA_TACTICAL_BEHAVIOR_CONTEXT",
        },
        "fundamental_invalidation": fundamental_invalidation,
        "evidence_gaps": evidence_gaps,
        "lineage": {
            "financial_analysis_source_identity": fa_record.get("lineage_ref") if fa_record else None,
            "financial_analysis_as_of_period": fa_record.get("as_of_financial_period") if fa_record else None,
            "corporate_event_source_session": (event_record or {}).get("research_session") if event_record else None,
        },
        "method_versions": {
            "invalidation": METHOD_INVALIDATION, "supporting_and_counter_evidence": METHOD_EVIDENCE,
            "risk_evidence": METHOD_RISK, "catalyst_classification": CATALYST_METHOD_VERSION,
        },
        "authority_boundaries": {
            "research_only": True, "case_is_not_decision_authority": True, "no_probability": True,
            "no_target_price": True, "no_expected_return": True, "no_action": True, "no_sizing": True,
            "no_universal_thesis_score": True,
        },
    }


def build_artifact(*, as_of_session: str, requested_at: str, daily_tickers: Any,
                    financial_analysis_product_context: Mapping[str, Any] | None,
                    events: Mapping[str, Any] | None) -> dict[str, Any]:
    """Build ``current_thesis_case_context/v1`` over exactly ``daily_tickers`` -- never wider,
    never narrower. ``daily_tickers`` should be the same Daily ticker set (watchlist union
    valuation) the canonical current chain already computes; passing anything else risks either
    silently dropping a Daily ticker or introducing one the rest of the chain does not carry."""
    tickers = sorted(set(daily_tickers))
    if not tickers:
        raise ThesisCaseContextError("EMPTY_THESIS_CASE_DENOMINATOR")
    event_records = (events or {}).get("records") if isinstance(events, Mapping) else None
    event_records = event_records if isinstance(event_records, Mapping) else {}
    event_contract_version = (events or {}).get("contract_version") if isinstance(events, Mapping) else None
    records: dict[str, dict[str, Any]] = {}
    for ticker in tickers:
        fa_record = _fa_record(financial_analysis_product_context, ticker)
        event_record = event_records.get(ticker)
        records[ticker] = build_ticker_case(
            ticker=ticker, as_of_session=as_of_session, fa_record=fa_record,
            event_record=event_record if isinstance(event_record, Mapping) else None,
            event_contract_version=event_contract_version,
        )
    if set(records) != set(tickers):
        raise ThesisCaseContextError("THESIS_CASE_SILENT_TICKER_DROP")

    case_class_counts = Counter()
    for record in records.values():
        for case_class in record["case_classes_present"]:
            case_class_counts[case_class] += 1
    fundamental_invalidation_status = Counter(record["fundamental_invalidation"]["status"] for record in records.values())
    presentation_only_sourced = 0  # invariant proof value; always 0 -- see docs/canonical_evidence_bound_thesis_cases_replay_20260913.md

    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "contract_version": CONTRACT_VERSION, "milestone": MILESTONE,
        "requested_at": requested_at, "as_of_session": as_of_session,
        "source_artifacts": {
            "financial_analysis_product_context": (financial_analysis_product_context or {}).get("artifact_identity"),
            "corporate_event_context": (events or {}).get("artifact_identity"),
        },
        "denominator": len(records),
        "coverage": {
            "ticker_denominator": len(records),
            "zero_silent_ticker_drops": True,
            "tickers_with_ge_1_eligible_case": sum(bool(record["case_classes_present"]) for record in records.values()),
            "tickers_with_zero_eligible_cases": sum(not record["case_classes_present"] for record in records.values()),
            "case_class_ticker_counts": dict(sorted(case_class_counts.items())),
            "catalyst_method_identity": CATALYST_METHOD_VERSION,
            "fundamental_invalidation_status": dict(sorted(fundamental_invalidation_status.items())),
            "presentation_only_sourced_cases": presentation_only_sourced,
        },
        "blocked_outputs": {
            "probability_of_success": "FORECAST_PROHIBITED", "target_price": "NOT_EMITTED",
            "expected_return": "NOT_EMITTED", "action": "NOT_EMITTED", "position_size": "NOT_EMITTED",
            "universal_thesis_score": "SCORING_PROHIBITED",
        },
        "records": records,
        "authority_effect": "NONE / DETERMINISTIC_THESIS_CONTEXT_MATERIALIZATION_AND_INTEGRATION_ONLY",
    }
    artifact.update(_identity(artifact))
    return artifact
