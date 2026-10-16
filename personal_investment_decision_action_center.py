"""Personal Investment Decision Action Center (PERSONAL_INVESTMENT_DECISION_ACTION_CENTER_V1).

Turns Stock Lookup's existing research engines into one deterministic owner-facing daily decision
surface. This module computes NO new decision: every field below is read straight from an
already-materialized, already-governed retained artifact for one completed session --
``integrated_investment_decision_product/v1`` (research_action_posture, trigger, invalidation,
counter-thesis, evidence axes), ``asymmetric_dislocation_research/v1`` (discovery lanes),
``market_wide_current_descriptive_research/v1`` and ``current_market_sector_leadership_context/v1``
(market regime), and -- only when a private local portfolio is present -- the just-released
``portfolio_aware_decision/v1`` current-position-truth chain (``CURRENT_CONFIRMED`` /
``CLOSED`` / ``CURRENT_POSITION_UNRESOLVED``, ``PERSONAL_DECISION_INPUT_TRUTH_V1``). It only
selects, remaps to a bounded action vocabulary, and re-presents.

Seven sections, in the order an owner reads them: MARKET, PORTFOLIO (confirmed holdings only --
``CURRENT_POSITION_UNRESOLVED`` and owner-excluded tickers are structurally excluded, never
just filtered by convention), UNRESOLVED_PORTFOLIO (review-only, no BUY/SELL derived from an
uncertain holding), WATCHLIST (the governed owner-focus config, not portfolio holdings), DISCOVERY
(the full research universe, portfolio-independent), CAPITAL_ROTATION (research comparison only,
never sourced from an unresolved position), and ATTENTION_QUEUE (categorical, never a score).

No universal stock score, no fabricated probability, no fabricated target price, no execution
order -- this module inherits every one of those boundaries unchanged from its sources; it has no
authority to create any of them itself.

Private-portfolio-optional by design (``AI_RULES.md``: a system authority gap must not
automatically produce WAIT): MARKET / WATCHLIST / DISCOVERY / a general ATTENTION_QUEUE are always
produced from public retained artifacts alone. PORTFOLIO / UNRESOLVED_PORTFOLIO / CAPITAL_ROTATION
require a private local portfolio and degrade to an explicit ``PRIVATE_PORTFOLIO_NOT_SUPPLIED``
status when one is not present -- never a silent empty result indistinguishable from "no holdings".

Local-only output: the qualified workspace's private sibling when explicitly selected,
otherwise ``%USERPROFILE%\\.stocklookup\\action_center\\<session>\\``. Never
written to Git, ``operations-review/``, the Dashboard, or the public
``current_research_ai_handoff_packet``/``stocklookup-ai-handoffs`` path -- even the
private-portfolio-free baseline, because the whole point of this product is the owner's own local
daily read, not a second public artifact. No second AI reasoning engine: the JSON artifact is
already structured enough for an external AI research consumer to explain without recomputing
anything; nothing here calls one.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

import asymmetric_dislocation_research as _asymmetric
import next_session_decision_brief as _next_session
import stocklookup_core.decision.integrated_investment_decision_product as _integrated
import owner_research_exclusions as _owner_research_exclusions
import owner_research_focus as _owner_focus
import stocklookup_core.portfolio.personal_portfolio_quant_risk_decomposition as _quant
import stocklookup_core.portfolio.portfolio_aware_decision as _pad
import stocklookup_core.portfolio.private_portfolio_context as _private_portfolio_context

CONTRACT_VERSION = "personal_investment_decision_action_center/v1"
MILESTONE = "PERSONAL_INVESTMENT_DECISION_ACTION_CENTER_V1"

# ── Bounded action vocabularies (pure remaps of already-computed posture/portfolio_action_research
# -- no new threshold or scoring logic anywhere in this module). ──────────────────────────────────
HOLDING_ACTIONS = frozenset({
    "ADD_CANDIDATE", "HOLD", "HOLD_NO_ADD", "REDUCE_REVIEW", "EXIT_REVIEW", "WAIT_FOR_CONFIRMATION",
})
WATCHLIST_ACTIONS = frozenset({"BUY_PROBE_CANDIDATE", "WAIT_FOR_CONFIRMATION", "WATCH", "AVOID_NEW_ENTRY"})
DISCOVERY_LANES = ("TACTICAL_SETUP", "EARLY_REVERSAL", "VALUATION_DISLOCATION", "ASYMMETRIC_RECOVERY_CASE")
ATTENTION_BUCKETS = ("ACTION_REVIEW_NOW", "PORTFOLIO_DATA_REVIEW", "THESIS_REVIEW", "CONFIRMATION_WATCH", "NO_ACTION_REQUIRED")
_ATTENTION_PRIORITY = {name: index for index, name in enumerate(ATTENTION_BUCKETS)}

# Asymmetric-dislocation states this module treats as a genuine opportunity candidate vs a risk
# flag -- reusing exactly the same split ``portfolio_aware_opportunity_shortlist.py`` already
# established (``_RECOVERY``/``_RISK``), not a new classification.
_ASYMMETRIC_OPPORTUNITY_LANE = {
    "QUALITY_DISLOCATION": "VALUATION_DISLOCATION",
    "TURNAROUND_EVIDENCE_FORMING": "ASYMMETRIC_RECOVERY_CASE",
    "CYCLICAL_RECOVERY_FORMING": "ASYMMETRIC_RECOVERY_CASE",
}
_TACTICAL_SETUP_POSTURES = frozenset({"INITIATE_ON_BREAKOUT", "ACCUMULATE_ON_RETEST"})
_EARLY_REVERSAL_POSTURES = frozenset({"EARLY_WATCH"})

_ROTATION_DESTINATION_LIMIT = 5


class ActionCenterError(ValueError):
    pass


def default_action_center_root() -> Path:
    """The sole default local storage root; deliberately outside Git, a sibling of the private
    portfolio root but independent of it -- this product does not require a private portfolio."""
    from runtime_paths import workspace_profile
    profile = workspace_profile()
    if profile:
        destination = profile["paths"]["logs"].parent / "private-action-center"
        if destination.is_symlink() or destination.is_junction():
            raise ActionCenterError("PRIVATE_ACTION_CENTER_ROOT_REDIRECTED")
        return destination
    user_profile = os.environ.get("USERPROFILE")
    return Path(user_profile) / ".stocklookup" / "action_center" if user_profile else Path.home() / ".stocklookup" / "action_center"


def evaluate_selected_research_preview(*, repo_root: Path, session: str, tickers: Sequence[str],
                                       current_operation: Path, previous_operation: Path | None = None) -> dict[str, Any]:
    """Opt-in focused preview; fully verify original sources, never invoke the full builder.

    Operations are explicit locators. The previous date is selected independently from the
    qualified registry chain, then checked against the supplied immutable operation manifest.
    No private portfolio input, Daily invocation, or evidence/publication write exists here.
    """
    import time
    from collections import Counter
    from stocklookup_core.decision import bounded_research_preview as bounded
    from stocklookup_core.evidence.field_identity import stable_id
    from stocklookup_core.tactical import watchlist_tactical_entry_classifier as tactical_owner

    bounded.resource_gate()
    selected = bounded.select_tickers(tickers)
    deadline = time.monotonic() + bounded.DEADLINE_SECONDS
    root = Path(repo_root).resolve()
    registry = bounded.small_json(root / "config/daily_research_session_input_registry.json")
    if registry.get("contract_version") != "daily_research_session_input_registry/v1":
        raise ActionCenterError("PREVIEW_REGISTRY_CONTRACT_MISMATCH")
    _next_session._require_qualified(registry, session)
    chain = _next_session._qualified_session_chain(registry)
    prior_dates = [date for date in chain if date < session]
    previous_session = prior_dates[-1] if prior_dates else None
    if (previous_session is None) != (previous_operation is None):
        raise ActionCenterError("PREVIEW_PREVIOUS_QUALIFIED_OPERATION_REQUIRED_OR_UNEXPECTED")

    def resolve(date, operation):
        _next_session._require_qualified(registry, date)
        if registry["completed_sessions"][date].get("trading_day_valid") is not True:
            raise ActionCenterError("PREVIEW_COMPLETED_TRADING_SESSION_NOT_QUALIFIED")
        selection = _next_session.registered_session_selection(registry, date)
        locked = _next_session.frozen_input_identities(registry, date)
        if {k: v["artifact_identity"] for k, v in selection.items()} != locked:
            raise ActionCenterError("PREVIEW_COMPLETED_INPUT_LOCK_MISMATCH")
        manifest = bounded.small_json(Path(operation) / "run_manifest.json")
        expected_operation = "daily_research_session_operation:" + stable_id(
            {k: v for k, v in manifest.items() if k != "operation_identity"})
        if (manifest.get("contract_version") != "daily_research_session_operation/v1"
                or manifest.get("schema_version") != "1.0.0"
                or manifest.get("generation_context") != "DAILY_PRODUCER_RETAINED_COMPLETED_SESSION"
                or manifest.get("market_session") != date
                or manifest.get("operation_identity") != expected_operation):
            raise ActionCenterError("PREVIEW_OPERATION_IDENTITY_OR_SESSION_MISMATCH")
        native_operation = root / "operations-review/daily-research-session-operations-v1" / date / expected_operation.split(":")[1]
        if Path(operation).resolve() != native_operation.resolve():
            raise ActionCenterError("PREVIEW_UNREGISTERED_OPERATION_LOCATOR")
        manifest_inputs = manifest.get("input_artifacts") or {}
        # build_operation adds these two separate optional inputs outside the session registry.
        # They are not read or consumed by this preview. Every frozen input must still match.
        if (set(manifest_inputs) - set(locked) - {"macro", "explicit_portfolio"}
                or {k: (manifest_inputs.get(k) or {}).get("artifact_identity") for k in locked} != locked):
            raise ActionCenterError("PREVIEW_MANIFEST_INPUT_REFERENCE_MISMATCH")
        expected_iid = (manifest.get("outputs") or {}).get("integrated_investment_decision_product")
        if not isinstance(expected_iid, str):
            raise ActionCenterError("PREVIEW_MANIFEST_INTEGRATED_REFERENCE_REQUIRED")
        # Native session locator, same path as session_artifact_paths; no latest/glob discovery.
        iid_path = root / "operations-review" / ("integrated-investment-decision-product-v1-" + date.replace("-", "")) / "integrated_investment_decision_product_artifact.json"
        projection = bounded.verified_projection(iid_path, session=date, expected_identity=expected_iid,
                                                 tickers=selected, deadline=deadline)
        tactical_entry = selection["tactical"]
        tactical_path = (root / tactical_entry["path"]).resolve()
        if not tactical_path.is_relative_to(root):
            raise ActionCenterError("PREVIEW_REGISTERED_PATH_OUTSIDE_EVIDENCE_ROOT")
        tactical = bounded.small_json(tactical_path, limit=16 * 1024 * 1024)
        if (tactical.get("session") != date or tactical.get("contract_version") != tactical_owner.CONTRACT_VERSION
                or tactical.get("artifact_identity") != tactical_entry["artifact_identity"]
                or any(tactical.get(k) != v for k, v in tactical_owner.content_identity(tactical).items())):
            raise ActionCenterError("PREVIEW_TACTICAL_SOURCE_IDENTITY_MISMATCH")
        confirmed = {t for t in selected if (tactical.get("records", {}).get(t) or {}).get("entry_state")
                     in _next_session.TACTICAL_CONFIRMATION_STATES}
        projection["confirmed"] = confirmed
        projection["operation_identity"] = expected_operation
        projection["source_locator"] = iid_path.relative_to(root).as_posix()
        projection["tactical_identity"] = tactical_entry["artifact_identity"]
        return projection

    # Previous source graph is discarded record by record; only selected rows survive.
    previous = resolve(previous_session, previous_operation) if previous_session else None
    current = resolve(session, current_operation)

    def source_view(projection):
        if projection is None:
            return None
        return {**projection["source_metadata"], "records": projection["selected_records"]}

    prev_view, curr_view = source_view(previous), source_view(current)
    transitions = {}
    for ticker, row in current["selected_records"].items():
        if previous is None:
            continue
        prev = previous["selected_records"].get(ticker) if previous else None
        transitions[ticker] = {
            "transition": _expected_posture_label(prev, row, prev_view or {}, curr_view),
            "previous_posture": (prev or {}).get("research_action_posture"),
            "current_posture": row.get("research_action_posture"),
            "previous_decision_identity": (prev or {}).get("decision_identity"),
            "current_decision_identity": row.get("decision_identity"),
        }
    current_confirmed = current["confirmed"]
    previous_confirmed = previous["confirmed"] if previous else set()
    # Explicitly a selected transition projection, NOT a next_session_decision_brief artifact.
    context = {
        "current_session": session, "previous_qualified_session": previous_session,
        "posture_transition": {"records": transitions},
        "tactical_transition": {
            "availability": "AVAILABLE" if previous else "UNAVAILABLE",
            "reason_codes": [] if previous else ["NO_PREVIOUS_QUALIFIED_SESSION"],
            "gained_confirmation": sorted(current_confirmed - previous_confirmed) if previous else [],
            "retained_confirmation": sorted(current_confirmed & previous_confirmed),
            "lost_confirmation": sorted(previous_confirmed - current_confirmed),
        },
        "source_lineage": {"current": current["source_identity"],
                           "previous": previous["source_identity"] if previous else None},
    }
    context["artifact_identity"] = "selected_transition_projection:" + stable_id(context)
    entries = []
    numeric = Counter()
    numeric_reasons = Counter()
    unavailable_reasons = Counter()
    for ticker in selected:
        record = current["selected_records"].get(ticker)
        if record is None:
            continue
        bounded.validate_price_dimensions(previous["selected_records"].get(ticker) if previous else None, record)
        lineage = record.get("evidence_currency_lineage") or {}
        coverage = {ticker: lineage} if lineage.get("method") == _integrated.EVIDENCE_CURRENCY_SOURCE_CONTRACT else {}
        evidence = _evidence_block(ticker, record, session=session, coverage_records=coverage)
        # Base condensed display is narrowed to the conditional qualification rule too.
        details = _conditional_research_details(record, evidence)
        for role in ("trigger", "invalidation"):
            boundary = details[role]
            if not (boundary.get("price_basis") or {}).get("price_unit"):
                boundary["numeric_display_status"] = "WITHHELD_UNQUALIFIED_BOUNDARY"
                boundary["numeric_display_reason_codes"].append("PRICE_UNIT_NOT_QUALIFIED")
                boundary[role + "_level"] = boundary["distance_to_" + role + "_pct"] = None
                for condition_key in ("condition", "watchlist_condition"):
                    if isinstance(boundary.get(condition_key), dict):
                        boundary[condition_key]["reference_level"] = None
            evidence[role] = copy.deepcopy(details[role])
            numeric[details[role]["numeric_display_status"]] += 1
            numeric_reasons.update(details[role]["numeric_display_reason_codes"])
        evidence["conditional_research"] = details
        transition = _setup_transition_for_ticker(session=session, ticker=ticker, current_artifact=curr_view,
                                                previous_artifact=prev_view, brief=context)
        transition["source_lineage"]["selected_transition_projection"] = transition["source_lineage"].pop("next_session_decision_brief")
        if "source" in transition["tactical_confirmation"]:
            transition["tactical_confirmation"]["source"] = "verified_registered_tactical_selected_projection"
        unavailable_reasons.update(transition["reason_codes"])
        if transition["status"] == "NOT_COMPARABLE":
            for field in transition["setup_context"].values():
                field["status"] = "NOT_COMPARABLE_POLICY_CHANGE"
        prev_record = (previous["selected_records"].get(ticker) if previous else None)
        if prev_record and not _next_session.fundamental_signals.epochs_comparable(prev_record, record):
            transition["research_limitations"].append("FUNDAMENTAL_POLICY_EPOCH_CHANGE_NO_FUNDAMENTAL_EVOLUTION_INFERENCE")
            transition["setup_context"]["fundamental_state"]["status"] = "NOT_COMPARABLE_POLICY_CHANGE"
            unavailable_reasons["FUNDAMENTAL_POLICY_EPOCH_CHANGE"] += 1
        if previous and ticker not in previous["selected_records"]:
            unavailable_reasons["PREVIOUS_SELECTED_RECORD_ABSENT"] += 1
        details["setup_transition"] = transition
        entries.append({"ticker": ticker, "evidence": evidence})
    counts = Counter(row["transition"] for row in transitions.values())
    missing = sorted(set(selected) - set(current["selected_records"]))

    def proof(projection):
        if projection is None:
            return None
        return {k: projection[k] for k in ("source_identity", "source_locator", "source_record_count",
                "source_bytes", "verification", "operation_identity", "tactical_identity")}

    body = {
        "contract_version": bounded.CONTRACT, "session": session,
        "previous_qualified_session": previous_session,
        "scope": {"kind": "FOCUSED_SELECTED_PREVIEW_NOT_FULL_ACTION_CENTER",
                  "selection_rule": "EXPLICIT_TICKER_SELECTION", "selected_tickers": list(selected),
                  "selected_record_count": len(entries), "requested_ticker_count": len(selected),
                  "full_source_denominator": current["source_record_count"],
                  "excluded_source_record_count": current["source_record_count"] - len(entries),
                  "unavailable_selected_tickers": missing, "statistics_scope": "SELECTED_TICKERS_ONLY"},
        "verification": "FULL_NATIVE_CONTENT_VERIFIED", "source_proofs": {"previous": proof(previous), "current": proof(current)},
        "selected_statistics": {"transition_counts": dict(sorted(counts.items())),
            "unchanged_postures": counts["POSTURE_UNCHANGED"],
            "setup_to_confirmation_events": counts["WAIT_TO_INITIATE"] + counts["EARLY_WATCH_TO_INITIATE"],
            "failed_or_invalidated_setups": counts["BREAKOUT_FAILED"] + counts["UPTREND_TO_BREAKDOWN"],
            "qualified_comparable_tickers": sum(1 for e in entries if previous
                and e["ticker"] in previous["selected_records"]
                and e["evidence"]["conditional_research"]["setup_transition"]["status"] == "AVAILABLE"
                and _next_session.fundamental_signals.epochs_comparable(
                    previous["selected_records"][e["ticker"]], current["selected_records"][e["ticker"]])),
            "early_watch_persistence": sum(1 for t in transitions.values() if t["current_posture"] == t["previous_posture"] == "EARLY_WATCH"),
            "priority_posture_disagreements": sum(1 for e in entries if
                (e["evidence"]["conditional_research"]["opportunity_priority"] or {}).get("research_priority_tier") == "PRIORITY_NOW"
                and e["evidence"]["research_action_posture"] == "WAIT_FOR_CONFIRMATION"),
            "numeric_boundaries": dict(sorted(numeric.items())),
            "numeric_withholding_reasons": dict(sorted(numeric_reasons.items())),
            "missing_or_noncomparable_reasons": dict(sorted(unavailable_reasons.items())),
            "unavailable_selected_count": len(missing)},
        "entries": entries, "private_portfolio": "NOT_REQUESTED_OR_READ",
        "authority_boundary": {"is_actionable": False, "authority_effect": "NONE",
                               "valuation_sizing_execution": "NO_ADDITIONAL_AUTHORITY"},
    }
    body.update(bounded.identity(body))
    return body


def selected_research_preview_markdown(artifact: Mapping[str, Any]) -> str:
    """Render only the explicit preview contract using the existing investor evidence renderer."""
    from stocklookup_core.decision import bounded_research_preview as bounded
    if artifact.get("contract_version") != bounded.CONTRACT or any(
        artifact.get(k) != v for k, v in bounded.identity(artifact).items()
    ):
        raise ActionCenterError("PREVIEW_RENDER_CONTRACT_OR_IDENTITY_MISMATCH")
    scope = artifact["scope"]
    lines = ["# Selected research preview", "", f"Session {artifact['session']}; previous qualified session {artifact['previous_qualified_session'] or 'NONE'}.",
             f"Focused preview: {scope['selected_record_count']} selected records / {scope['full_source_denominator']} full source records; {scope['excluded_source_record_count']} excluded. Selection: {scope['selection_rule']}.",
             f"Source verification: {artifact['verification']}. Statistics cover selected tickers only.",
             "This is not a full Action Center. Private portfolio was not requested or read. No valuation, sizing or execution authority is added.", ""]
    for entry in artifact["entries"]:
        lines.extend([f"## {entry['ticker']}", "", *_md_conditional_research(entry["evidence"]), ""])
    if scope["unavailable_selected_tickers"]:
        lines.append("Unavailable selected tickers: " + ", ".join(scope["unavailable_selected_tickers"]))
    return "\n".join(lines) + "\n"


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(body: Mapping[str, Any]) -> dict[str, str]:
    payload = {key: item for key, item in body.items() if key not in {"artifact_identity", "artifact_sha256", "requested_at"}}
    digest = hashlib.sha256(_canon(payload).encode("utf-8")).hexdigest()
    return {"artifact_sha256": digest, "artifact_identity": f"{CONTRACT_VERSION}:{digest}"}


# ── Per-ticker evidence condensation (read-only projection of integrated_investment_decision_product) ──

def _condensed_trigger(trigger: Mapping[str, Any] | None, *, price_fresh: bool) -> dict[str, Any]:
    trigger = trigger or {}
    # PERSONAL_INVESTMENT_DECISION_ACTION_CENTER_V1 fail-closed rule: a numeric, price-sensitive
    # trigger distance is never shown next to a stale price mark -- the qualitative trigger_state/
    # warning still passes through unchanged (this is a narrowing, never a widening, of what the
    # producer already asserted).
    return {
        "trigger_type": trigger.get("trigger_type"),
        "trigger_level": trigger.get("trigger_level") if price_fresh else None,
        "distance_to_trigger_pct": trigger.get("distance_to_trigger_pct") if price_fresh else None,
        "trigger_state": trigger.get("trigger_state"),
        "warning": trigger.get("warning"),
        "numeric_fields_withheld_stale_price": not price_fresh,
    }


def _condensed_invalidation(invalidation: Mapping[str, Any] | None, *, price_fresh: bool) -> dict[str, Any]:
    invalidation = invalidation or {}
    return {
        "invalidation_level": invalidation.get("invalidation_level") if price_fresh else None,
        "distance_to_invalidation_pct": invalidation.get("distance_to_invalidation_pct") if price_fresh else None,
        "invalidation_method": invalidation.get("invalidation_method"),
        "warning": invalidation.get("warning"),
        "numeric_fields_withheld_stale_price": not price_fresh,
    }


def _condensed_axis(evidence_axes: Mapping[str, Any] | None, axis: str) -> dict[str, Any]:
    axis_record = (evidence_axes or {}).get(axis)
    if not isinstance(axis_record, Mapping):
        return {"fitness": "NOT_PROVIDED"}
    return {
        "fitness": axis_record.get("fitness"),
        "is_actionable": axis_record.get("is_actionable"),
        "contradicting_reason_codes": list(axis_record.get("contradicting_reason_codes") or []),
        "blocker_reason_codes": list(axis_record.get("blocker_reason_codes") or []),
    }


def _freshness(ticker: str, *, session: str, coverage_records: Mapping[str, Any] | None) -> dict[str, Any]:
    """The exact-session price/technical distinction this milestone's predecessor
    (PERSONAL_DECISION_INPUT_TRUTH_V1) fixed in the AI-handoff card: ``research_session`` is
    always this artifact's own session; ``technical_coverage_disposition`` is this ticker's own,
    already-computed same-session-or-not verdict (``same_session_technical_coverage_disposition``)
    when that artifact was supplied -- never re-derived here. ``price_freshness`` is a direct,
    un-widened remap of that disposition, never a new staleness judgment."""
    row = (coverage_records or {}).get(ticker)
    if not isinstance(row, Mapping):
        return {"research_session": session, "technical_coverage_disposition": "NOT_EVALUATED", "price_freshness": "NOT_EVALUATED"}
    disposition = row.get("disposition")
    fresh = disposition == "SAME_SESSION_TECHNICAL_COVERED"
    return {
        "research_session": session,
        "technical_coverage_disposition": disposition,
        "price_freshness": "CURRENT" if fresh else "STALE_OR_UNAVAILABLE",
    }


def _evidence_block(ticker: str, record: Mapping[str, Any], *, session: str, coverage_records: Mapping[str, Any] | None) -> dict[str, Any]:
    freshness = _freshness(ticker, session=session, coverage_records=coverage_records)
    price_fresh = freshness["price_freshness"] == "CURRENT"
    evidence_axes = record.get("evidence_axes") or {}
    corporate_intelligence = record.get("corporate_intelligence_context") or {}
    return {
        "why_now": record.get("why_now"),
        "research_action_posture": record.get("research_action_posture"),
        "posture_condition_class": record.get("posture_condition_class"),
        "research_action_policy_version": record.get("research_action_policy_version", "v1"),
        # Producer-owned evidence currency, passed through. The ``freshness`` block below stays a
        # diagnostic explanation only; it never re-derives a competing decision-currency class.
        "evidence_currency": record.get("evidence_currency"),
        "tactical_phase": record.get("tactical_phase"),
        "market_structure_state": record.get("market_structure_state"),
        "fundamental_state": record.get("fundamental_state"),
        "valuation_context_summary": record.get("valuation_context_summary"),
        "market_sector_context": record.get("market_sector_context"),
        "catalyst_state": {
            "fitness": corporate_intelligence.get("fitness"),
            "active_catalyst_count": corporate_intelligence.get("active_catalyst_count"),
            "active_risk_count": corporate_intelligence.get("active_risk_count"),
            "evidence_session": corporate_intelligence.get("evidence_session"),
            "evidence_session_stale": corporate_intelligence.get("evidence_session_stale"),
        },
        "trigger": _condensed_trigger(record.get("trigger"), price_fresh=price_fresh),
        "invalidation": _condensed_invalidation(record.get("invalidation"), price_fresh=price_fresh),
        "counter_thesis": list(record.get("counter_thesis") or []),
        "material_uncertainties": list(record.get("material_uncertainties") or []),
        "evidence_axes_summary": {
            "TACTICAL_STRUCTURE": _condensed_axis(evidence_axes, "TACTICAL_STRUCTURE"),
            "FUNDAMENTAL": _condensed_axis(evidence_axes, "FUNDAMENTAL"),
            "VALUATION": _condensed_axis(evidence_axes, "VALUATION"),
            "CORPORATE_INTELLIGENCE": _condensed_axis(evidence_axes, "CORPORATE_INTELLIGENCE"),
            "MARKET_SECTOR": _condensed_axis(evidence_axes, "MARKET_SECTOR"),
        },
        "freshness": freshness,
        "source_identities": {"decision_identity": record.get("decision_identity")},
    }


def _conditional_research_details(record: Mapping[str, Any], evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Restate retained conditions and independent lenses; never evaluate a future event."""
    details = {key: copy.deepcopy(record.get(key)) for key in (
        "opportunity_priority", "priority_posture_reconciliation", "breakout_state_v3",
        "technical_support", "fundamental_support", "fundamental_evidence_availability",
        "fundamental_synthesis", "exact_capabilities_unavailable", "missing_evidence_decision_effect",
        "evidence_currency_lineage", "source_identities",
        "legacy_comparison",
    )}
    for role in ("trigger", "invalidation"):
        boundary = copy.deepcopy(record.get(role) or {})
        basis = boundary.get("price_basis") or {}
        condition = boundary.get("condition") or {}
        reasons = []
        if (evidence.get("freshness") or {}).get("price_freshness") != "CURRENT":
            reasons.append("CURRENT_PRICE_NOT_ESTABLISHED")
        if record.get("evidence_currency") != _integrated.EVIDENCE_CURRENCY_CURRENT_SESSION:
            reasons.append("CANONICAL_CURRENT_EVIDENCE_NOT_ESTABLISHED")
        if basis.get("price_basis_verified") is not True:
            reasons.append("PRICE_BASIS_UNVERIFIED")
        if condition.get("status") != "MACHINE_EVALUABLE":
            reasons.append("CONDITION_NOT_MACHINE_EVALUABLE")
        elif condition.get("reference_level") != boundary.get(f"{role}_level"):
            reasons.append("CONDITION_AND_BOUNDARY_LEVEL_CONFLICT")
        numeric_allowed = not reasons
        # Descriptive conditions survive unknown basis/freshness. Numeric display is
        # narrower than the retained measurement; never label an unverified unit VND.
        if not numeric_allowed:
            for key in (f"{role}_level", f"distance_to_{role}_pct"):
                boundary[key] = None
            for key in ("condition", "watchlist_condition"):
                if isinstance(boundary.get(key), dict):
                    boundary[key]["reference_level"] = None
        for key in ("condition", "watchlist_condition"):
            if isinstance(boundary.get(key), dict):
                # The source hash identifies the retained condition, not this narrowed view.
                boundary[key]["source_condition_identity"] = boundary[key].pop("condition_identity", None)
        boundary["numeric_display_status"] = "AVAILABLE" if numeric_allowed else "WITHHELD_UNQUALIFIED_BOUNDARY"
        boundary["numeric_display_reason_codes"] = reasons
        details[role] = boundary
    details["authority"] = "EXPLANATION_ONLY_NO_POSTURE_OR_EVENT_RECOMPUTATION"
    return details


_SETUP_CONTEXT_FIELDS = (
    "breakout_state_v3", "tactical_phase", "market_structure_state",
    "fundamental_state", "fundamental_evidence_availability",
)


def _observed_field(previous: Mapping[str, Any] | None, current: Mapping[str, Any] | None, key: str) -> dict[str, Any]:
    """Compare one already-retained label. A difference is not a cause."""
    if not isinstance(current, Mapping):
        return {"status": "UNAVAILABLE", "previous": None, "current": None}
    if not isinstance(previous, Mapping):
        return {"status": "PREVIOUS_RECORD_ABSENT", "previous": None, "current": current.get(key)}
    previous_value, current_value = previous.get(key), current.get(key)
    if previous_value is None and current_value is None:
        status = "UNAVAILABLE"
    elif previous_value == current_value:
        status = "UNCHANGED"
    else:
        status = "CHANGED"
    return {"status": status, "previous": previous_value, "current": current_value}


def _expected_posture_label(
    previous_record: Mapping[str, Any] | None, current_record: Mapping[str, Any] | None,
    previous_artifact: Mapping[str, Any], current_artifact: Mapping[str, Any],
) -> str:
    """Mirror ``next_session_decision_brief._posture_transition``; do not add a label."""
    previous_epoch = (previous_record or {}).get(
        "research_action_policy_version", previous_artifact.get("research_action_policy_version", "v1"))
    current_epoch = (current_record or {}).get(
        "research_action_policy_version", current_artifact.get("research_action_policy_version", "v1"))
    if previous_epoch != current_epoch:
        return "NOT_COMPARABLE_POLICY_CHANGE"
    return _next_session._classify_posture_transition(previous_record, current_record)


def _require_setup_transition_brief(
    *, session: str, current_artifact: Mapping[str, Any],
    previous_artifact: Mapping[str, Any] | None, brief: Mapping[str, Any],
) -> None:
    if brief.get("contract_version") != _next_session.CONTRACT_VERSION:
        raise ActionCenterError("SETUP_TRANSITION_CONTRACT_MISMATCH")
    if brief.get("current_session") != session or current_artifact.get("session") != session:
        raise ActionCenterError("SETUP_TRANSITION_CURRENT_SESSION_MISMATCH")
    if any(brief.get(key) != value for key, value in _next_session.content_identity(brief).items()):
        raise ActionCenterError("SETUP_TRANSITION_ARTIFACT_IDENTITY_MISMATCH")
    boundary = brief.get("authority_boundary") or {}
    if boundary.get("is_actionable") is not False or boundary.get("derived_evidence_not_new_factual_authority") is not True:
        raise ActionCenterError("SETUP_TRANSITION_AUTHORITY_MISMATCH")
    posture = brief.get("posture_transition") or {}
    lineage = posture.get("source_lineage") or {}
    if lineage.get("current_integrated_decision_identity") != current_artifact.get("artifact_identity"):
        raise ActionCenterError("SETUP_TRANSITION_CURRENT_DECISION_LINEAGE_MISMATCH")
    previous_session = brief.get("previous_qualified_session")
    if previous_artifact is None:
        if previous_session is not None or posture.get("records") or "NO_PREVIOUS_QUALIFIED_SESSION" not in (posture.get("reason_codes") or []):
            raise ActionCenterError("SETUP_TRANSITION_PREVIOUS_INTEGRATED_ARTIFACT_REQUIRED")
        return
    if previous_artifact.get("session") != previous_session or not previous_session or previous_session >= session:
        raise ActionCenterError("SETUP_TRANSITION_PREVIOUS_SESSION_MISMATCH")
    if lineage.get("previous_integrated_decision_identity") != previous_artifact.get("artifact_identity"):
        raise ActionCenterError("SETUP_TRANSITION_PREVIOUS_DECISION_LINEAGE_MISMATCH")
    if posture.get("availability") != "AVAILABLE":
        raise ActionCenterError("SETUP_TRANSITION_POSTURE_SECTION_NOT_AVAILABLE")


_TACTICAL_LABEL_CONFLICTS = {
    "WAIT_TO_INITIATE": frozenset({"LOST_CONFIRMATION"}),
    "EARLY_WATCH_TO_INITIATE": frozenset({"LOST_CONFIRMATION"}),
    "BREAKOUT_FAILED": frozenset({"GAINED_CONFIRMATION", "RETAINED_CONFIRMATION"}),
}


def _tactical_confirmation(
    ticker: str, tactical: Mapping[str, Any] | None, *, comparable: bool, transition_label: str,
) -> dict[str, Any]:
    if not comparable:
        return {"status": "NOT_INTERPRETED", "reason_codes": ["NOT_COMPARABLE_POLICY_CHANGE"]}
    if not isinstance(tactical, Mapping):
        return {"status": "NOT_AVAILABLE", "reason_codes": ["TACTICAL_TRANSITION_NOT_SUPPLIED"]}
    found = [name for name in ("gained_confirmation", "retained_confirmation", "lost_confirmation") if ticker in set(tactical.get(name) or [])]
    if len(found) > 1:
        raise ActionCenterError("SETUP_TRANSITION_TACTICAL_MEMBERSHIP_CONFLICT:" + ticker)
    status = "NOT_IN_CONFIRMATION_DELTA" if not found else found[0].upper()
    if status in _TACTICAL_LABEL_CONFLICTS.get(transition_label, frozenset()):
        raise ActionCenterError("SETUP_TRANSITION_TACTICAL_MEMBERSHIP_CONFLICT:" + ticker)
    if not found:
        return {"status": status, "availability": tactical.get("availability"), "reason_codes": list(tactical.get("reason_codes") or [])}
    return {"status": status, "availability": tactical.get("availability"), "reason_codes": [], "source": "next_session_decision_brief.tactical_transition"}


def _price_basis_identity(record: Mapping[str, Any] | None) -> tuple[Any, Any] | None:
    basis = ((record or {}).get("trigger") or {}).get("price_basis")
    if not isinstance(basis, Mapping):
        return None
    label, unit = basis.get("research_label"), basis.get("price_unit")
    if label is None or unit is None:
        return None
    return (label, unit)


def _setup_transition_for_ticker(
    *, session: str, ticker: str, current_artifact: Mapping[str, Any],
    previous_artifact: Mapping[str, Any] | None, brief: Mapping[str, Any],
) -> dict[str, Any]:
    current_records = current_artifact.get("records") or {}
    if ticker not in current_records:
        raise ActionCenterError("SETUP_TRANSITION_CURRENT_RECORD_MISSING:" + ticker)
    current = current_records[ticker]
    if previous_artifact is None:
        return {
            "status": "UNAVAILABLE", "reason_codes": ["NO_PREVIOUS_QUALIFIED_SESSION"],
            "current_session": session, "previous_qualified_session": None,
            "previous_research_action_posture": None, "current_canonical_posture": current.get("research_action_posture"),
            "governed_transition_label": None, "transition_is_not_an_outcome": True,
            "future_condition_is_not_a_triggered_event": True, "setup_context": {},
            "technical_market_sector_evidence": {}, "tactical_confirmation": {"status": "NOT_AVAILABLE", "reason_codes": ["NO_PREVIOUS_QUALIFIED_SESSION"]},
            "priority_posture_reconciliation": copy.deepcopy(current.get("priority_posture_reconciliation") or {}),
            "research_limitations": ["NO_PREVIOUS_QUALIFIED_SESSION_NO_TRANSITION_INVENTED"],
            "source_lineage": {"next_session_decision_brief": brief.get("artifact_identity"), "current_decision_identity": current.get("decision_identity"), "previous_decision_identity": None},
        }
    row = ((brief.get("posture_transition") or {}).get("records") or {}).get(ticker)
    if not isinstance(row, Mapping):
        raise ActionCenterError("SETUP_TRANSITION_TICKER_ROW_MISSING:" + ticker)
    previous = (previous_artifact.get("records") or {}).get(ticker)
    expected = _expected_posture_label(previous, current, previous_artifact, current_artifact)
    if row.get("transition") != expected or row.get("transition") not in _next_session.POSTURE_TRANSITION_LABELS:
        raise ActionCenterError("SETUP_TRANSITION_LABEL_MISMATCH:" + ticker)
    if row.get("current_posture") != current.get("research_action_posture") or row.get("current_decision_identity") != current.get("decision_identity"):
        raise ActionCenterError("SETUP_TRANSITION_CURRENT_DECISION_IDENTITY_MISMATCH:" + ticker)
    if previous is None:
        if row.get("previous_posture") is not None or row.get("previous_decision_identity") is not None:
            raise ActionCenterError("SETUP_TRANSITION_PREVIOUS_DECISION_IDENTITY_MISMATCH:" + ticker)
    elif row.get("previous_posture") != previous.get("research_action_posture") or row.get("previous_decision_identity") != previous.get("decision_identity"):
        raise ActionCenterError("SETUP_TRANSITION_PREVIOUS_DECISION_IDENTITY_MISMATCH:" + ticker)
    elif previous.get("as_of_session") != brief.get("previous_qualified_session"):
        raise ActionCenterError("SETUP_TRANSITION_PREVIOUS_SESSION_MISMATCH:" + ticker)
    previous_basis, current_basis = _price_basis_identity(previous), _price_basis_identity(current)
    price_label_changed = False
    if previous is not None and previous_basis is not None and current_basis is not None and previous_basis[1] != current_basis[1]:
        raise ActionCenterError("SETUP_TRANSITION_PRICE_BASIS_CONFLICT:" + ticker)
    if previous is not None and previous_basis is not None and current_basis is not None and previous_basis[0] != current_basis[0]:
        price_label_changed = True
    comparable = row.get("transition") != "NOT_COMPARABLE_POLICY_CHANGE"
    market = brief.get("market_transition") if isinstance(brief.get("market_transition"), Mapping) else {}
    market_transition = market.get("transition")
    market_direction = market_transition.get("advance_ratio_direction") if isinstance(market_transition, Mapping) else market_transition if isinstance(market_transition, str) else None
    current_market = current.get("market_sector_context") if isinstance(current.get("market_sector_context"), Mapping) else None
    previous_market = previous.get("market_sector_context") if isinstance(previous, Mapping) and isinstance(previous.get("market_sector_context"), Mapping) else None
    current_group = None if current_market is None else current_market.get("sector_group_key")
    previous_group = None if previous_market is None else previous_market.get("sector_group_key")
    if previous is not None and current_group != previous_group:
        sector_direction = "SECTOR_GROUP_KEY_CHANGED"
    else:
        sector_row = (((brief.get("sector_transition") or {}).get("sectors") or {}).get(current_group) if current_group else None)
        sector_direction = sector_row.get("transition") if isinstance(sector_row, Mapping) else None
    limitations = []
    if current.get("research_action_posture") == "EARLY_WATCH":
        limitations.append("EARLY_WATCH_IS_RESEARCH_POSTURE_NOT_CAPITAL_AUTHORIZATION")
    if (current.get("opportunity_priority") or {}).get("research_priority_tier") == "PRIORITY_NOW":
        limitations.append("PRIORITY_NOW_IS_RESEARCH_ATTENTION_NOT_BUY_NOW")
    if not comparable:
        limitations.append("POLICY_EPOCH_CHANGE_BLOCKS_CROSS_SESSION_INTERPRETATION")
    if current.get("fundamental_state") == _integrated.FUNDAMENTAL_INSUFFICIENT:
        limitations.append("FUNDAMENTAL_GAP_DOES_NOT_REMOVE_TECHNICAL_STATE")
    if price_label_changed:
        limitations.append("PRICE_BASIS_LABEL_CHANGED_NO_CROSS_SESSION_NUMERIC_COMPARISON")
    reconciliation = current.get("priority_posture_reconciliation") or {}
    if reconciliation.get("integrated_posture") != current.get("research_action_posture"):
        raise ActionCenterError("SETUP_TRANSITION_RECONCILIATION_POSTURE_MISMATCH:" + ticker)
    return {
        "status": "AVAILABLE" if comparable else "NOT_COMPARABLE",
        "reason_codes": [] if comparable else ["NOT_COMPARABLE_POLICY_CHANGE"],
        "current_session": session, "previous_qualified_session": brief.get("previous_qualified_session"),
        "previous_research_action_posture": None if previous is None else previous.get("research_action_posture"),
        "current_canonical_posture": current.get("research_action_posture"),
        "governed_transition_label": row.get("transition"),
        "transition_is_not_an_outcome": True, "future_condition_is_not_a_triggered_event": True,
        "setup_context": {key: _observed_field(previous, current, key) for key in _SETUP_CONTEXT_FIELDS},
        "technical_market_sector_evidence": {
            "market_regime": _observed_field(previous_market, current_market, "market_regime"),
            "sector_leadership": _observed_field(previous_market, current_market, "sector_leadership"),
            "governed_market_direction": market_direction,
            "governed_sector_direction": sector_direction,
            "market_weakness_is_context_not_a_new_veto": True,
        },
        "tactical_confirmation": _tactical_confirmation(
            ticker, brief.get("tactical_transition") if isinstance(brief.get("tactical_transition"), Mapping) else None,
            comparable=comparable, transition_label=row.get("transition"),
        ),
        "priority_posture_reconciliation": copy.deepcopy(reconciliation),
        "research_limitations": limitations,
        "source_lineage": {
            "next_session_decision_brief": brief.get("artifact_identity"),
            "current_decision_identity": current.get("decision_identity"),
            "previous_decision_identity": None if previous is None else previous.get("decision_identity"),
        },
    }


def _build_decision_surface_index(
    integrated_decision_artifact: Mapping[str, Any], *, portfolio_aware_decision_artifact: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Full-universe (ticker, research_action_posture, evidence_currency) read model -- the same
    shared projection the AI brief carries -- plus explicit position context. No monetary value
    enters this index. Without a private portfolio every position is UNKNOWN, never NOT_HELD.
    Holding-specific portfolio actions stay in their own sections and are not conflated here."""
    index = _integrated.decision_surface_index(integrated_decision_artifact)
    supplied = isinstance(portfolio_aware_decision_artifact, Mapping)
    position_records = (portfolio_aware_decision_artifact or {}).get("records") or {} if supplied else {}
    for row in index["rows"]:
        # Reuses portfolio_aware_decision's own position_state vocabulary verbatim.
        state = (position_records.get(row["ticker"]) or {}).get("position_state") if supplied else None
        row["position_context"] = state or _integrated.POSITION_UNKNOWN_NOT_SUPPLIED
    index["position_context_source"] = "PRIVATE_PORTFOLIO_LOCAL" if supplied else "NOT_SUPPLIED"
    return index


# ── Action remaps (deterministic lookup tables over already-computed posture/portfolio fields) ────

def _holding_action(*, portfolio_action_research: str, posture: str) -> str:
    # `position_state` (HELD vs HELD_ABOVE_POLICY_CAP) is deliberately not consulted directly:
    # the over-limit case is already carried in `portfolio_action_research == "OVER_LIMIT_REVIEW"`,
    # and an AVOID/REDUCE posture overrides regardless of whether the position happens to be
    # over-weighted -- an existing thesis breaking is the same signal either way.
    if posture == "AVOID":
        return "EXIT_REVIEW"
    if posture == "REDUCE":
        return "REDUCE_REVIEW"
    if portfolio_action_research == "OVER_LIMIT_REVIEW":
        return "HOLD_NO_ADD"
    if portfolio_action_research in (
        "ADD_WITHIN_RISK_CEILING", "ADD_WITHIN_EVALUATED_CONSTRAINTS", "ADD_ELIGIBLE_SIZING_UNAVAILABLE",
        "PROBE_WITHIN_RISK_CEILING", "PROBE_WITHIN_EVALUATED_CONSTRAINTS", "PROBE_ELIGIBLE_SIZING_UNAVAILABLE",
    ):
        return "ADD_CANDIDATE"
    if posture in ("WAIT_FOR_CONFIRMATION", "EARLY_WATCH"):
        return "WAIT_FOR_CONFIRMATION"
    return "HOLD"


def _watchlist_action(posture: str) -> str:
    if posture in ("INITIATE_ON_BREAKOUT", "ACCUMULATE_ON_RETEST"):
        return "BUY_PROBE_CANDIDATE"
    if posture in ("WAIT_FOR_CONFIRMATION", "EARLY_WATCH"):
        return "WAIT_FOR_CONFIRMATION"
    if posture in ("AVOID", "REDUCE"):
        return "AVOID_NEW_ENTRY"
    return "WATCH"


# ── Section builders ────────────────────────────────────────────────────────────────────────────

def _build_market_section(
    *, session: str, descriptive: Mapping[str, Any] | None, sector_leadership: Mapping[str, Any] | None,
    previous_descriptive: Mapping[str, Any] | None, previous_session: str | None,
) -> dict[str, Any]:
    if not isinstance(descriptive, Mapping):
        return {"status": "NOT_AVAILABLE", "reason": "NO_RETAINED_DESCRIPTIVE_RESEARCH_FOR_SESSION"}
    breadth = descriptive.get("market_breadth") or {}
    market_block = (sector_leadership or {}).get("market") or {}
    groups = ((sector_leadership or {}).get("groups") or {}).get("records") or {}
    leading = sorted(
        (row.get("group_identity") for row in groups.values() if isinstance(row, Mapping) and row.get("leadership_state") == "LEADING"),
    )
    lagging = sorted(
        (row.get("group_identity") for row in groups.values() if isinstance(row, Mapping) and row.get("leadership_state") in ("LAGGING", "WEAK", "DETERIORATING")),
    )
    previous_breadth = (previous_descriptive or {}).get("market_breadth") if isinstance(previous_descriptive, Mapping) else None
    previous_comparison: dict[str, Any]
    if isinstance(previous_breadth, Mapping):
        def _delta(key: str) -> float | int | None:
            a, b = breadth.get(key), previous_breadth.get(key)
            if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
                return a - b
            return None
        previous_comparison = {
            "status": "AVAILABLE", "previous_session": previous_session,
            "advance_ratio_delta": _delta("advance_ratio"), "advancing_delta": _delta("advancing"), "declining_delta": _delta("declining"),
        }
    else:
        previous_comparison = {"status": "NOT_AVAILABLE", "previous_session": previous_session}
    return {
        "status": "AVAILABLE",
        "session": session,
        "market_regime": {
            "current_breadth_state": market_block.get("current_breadth_state") or (breadth.get("breadth_descriptor") or {}).get("descriptor"),
            "advance_ratio": breadth.get("advance_ratio"), "advancing": breadth.get("advancing"), "declining": breadth.get("declining"), "unchanged": breadth.get("unchanged"),
        },
        "momentum_participation": {
            "momentum_descriptor": (breadth.get("momentum_descriptor") or {}).get("descriptor"),
            "positive_momentum_ratio": market_block.get("positive_momentum_ratio"),
            "negative_momentum_ratio": market_block.get("negative_momentum_ratio"),
            "trend_participation": market_block.get("trend_participation"),
        },
        "sector_leadership": {
            "leading_groups": leading, "lagging_or_weak_groups": lagging,
            "available_group_count": ((sector_leadership or {}).get("groups") or {}).get("available_group_count"),
            "data_limited_group_count": ((sector_leadership or {}).get("groups") or {}).get("data_limited_group_count"),
        } if sector_leadership is not None else {"status": "NOT_AVAILABLE"},
        "warnings": list(market_block.get("warnings") or []),
        "previous_session_comparison": previous_comparison,
        "source_artifact_identities": {
            "market_wide_current_descriptive_research": descriptive.get("artifact_identity"),
            "current_market_sector_leadership_context": (sector_leadership or {}).get("artifact_identity"),
        },
    }


def _build_portfolio_sections(
    *, session: str, integrated_records: Mapping[str, Any], portfolio_artifact: Mapping[str, Any] | None,
    coverage_records: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Returns (portfolio_section, unresolved_section). Structurally excludes CLOSED and
    EXCLUDED_INACTIVE tickers -- they are simply absent from `portfolio_artifact["records"]`'s
    HELD/HELD_ABOVE_POLICY_CAP/CURRENT_POSITION_UNRESOLVED subsets, never a filtered-out flag a
    caller could accidentally ignore."""
    if not isinstance(portfolio_artifact, Mapping):
        return (
            {"status": "PRIVATE_PORTFOLIO_NOT_SUPPLIED", "holdings": []},
            {"status": "PRIVATE_PORTFOLIO_NOT_SUPPLIED", "items": []},
        )
    records = portfolio_artifact.get("records") or {}
    holdings: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for ticker, row in sorted(records.items()):
        position_state = row.get("position_state")
        integrated_record = integrated_records.get(ticker) or {}
        if position_state in ("HELD", "HELD_ABOVE_POLICY_CAP"):
            posture = row.get("security_research_action_posture")
            action = _holding_action(portfolio_action_research=row.get("portfolio_action_research"), posture=posture)
            holdings.append({
                "ticker": ticker,
                "action": action,
                "position_state": position_state,
                "portfolio_action_research": row.get("portfolio_action_research"),
                "current_weight": row.get("current_weight"),
                "current_weight_status": row.get("current_weight_status"),
                "binding_constraint": row.get("binding_constraint"),
                "research_size_envelope": row.get("research_size_envelope"),
                "evidence": _evidence_block(ticker, integrated_record, session=session, coverage_records=coverage_records),
            })
        elif position_state == "CURRENT_POSITION_UNRESOLVED":
            unresolved.append({
                "ticker": ticker,
                "status": "CURRENT_POSITION_UNRESOLVED",
                "note": "Owner reconciliation of the private workbook is required before any portfolio action for this ticker; no BUY/SELL is derived from an uncertain holding.",
                "portfolio_action_research": row.get("portfolio_action_research"),
            })
    return (
        {"status": "AVAILABLE", "holdings": holdings},
        {"status": "AVAILABLE", "items": unresolved},
    )


def _build_watchlist_section(
    *, session: str, integrated_records: Mapping[str, Any], owner_focus: Mapping[str, Any] | None,
    excluded_tickers: frozenset[str], coverage_records: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if owner_focus is None:
        return {"status": "NOT_AVAILABLE", "reason": "OWNER_FOCUS_CONFIG_UNAVAILABLE", "entries": []}
    entries: list[dict[str, Any]] = []
    for ticker in sorted(owner_focus.get("broader_watchlist") or ()):
        if ticker in excluded_tickers:
            continue
        record = integrated_records.get(ticker)
        if not isinstance(record, Mapping):
            entries.append({"ticker": ticker, "action": "WATCH", "owner_focus": ticker in set(owner_focus.get("owner_focus_tickers") or ()), "status": "NOT_EVALUATED_THIS_SESSION"})
            continue
        posture = record.get("research_action_posture")
        entries.append({
            "ticker": ticker, "action": _watchlist_action(posture),
            "owner_focus": ticker in set(owner_focus.get("owner_focus_tickers") or ()),
            "status": "AVAILABLE",
            "evidence": _evidence_block(ticker, record, session=session, coverage_records=coverage_records),
        })
    return {"status": "AVAILABLE", "entries": entries}


def _build_discovery_section(
    *, session: str, integrated_records: Mapping[str, Any], asymmetric_records: Mapping[str, Any],
    excluded_tickers: frozenset[str], held_tickers: frozenset[str], coverage_records: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Full research universe, deliberately independent of any private portfolio input --
    ``integrated_records``/``asymmetric_records`` are both public, market-wide artifacts."""
    lanes: dict[str, list[dict[str, Any]]] = {lane: [] for lane in DISCOVERY_LANES}
    for ticker in sorted(integrated_records):
        if ticker in excluded_tickers or ticker in held_tickers:
            continue
        record = integrated_records[ticker]
        posture = record.get("research_action_posture")
        if posture in _TACTICAL_SETUP_POSTURES:
            tactical_lane = "TACTICAL_SETUP"
        elif posture in _EARLY_REVERSAL_POSTURES:
            tactical_lane = "EARLY_REVERSAL"
        else:
            tactical_lane = None
        asymmetric_state = (asymmetric_records.get(ticker) or {}).get("primary_research_state")
        asymmetric_lane = _ASYMMETRIC_OPPORTUNITY_LANE.get(asymmetric_state)
        if tactical_lane is None and asymmetric_lane is None:
            continue
        evidence = _evidence_block(ticker, record, session=session, coverage_records=coverage_records)
        if tactical_lane is not None:
            lanes[tactical_lane].append({"ticker": ticker, "lane": tactical_lane, "reason": f"POSTURE:{posture}", "evidence": evidence})
        if asymmetric_lane is not None:
            lanes[asymmetric_lane].append({"ticker": ticker, "lane": asymmetric_lane, "reason": f"ASYMMETRIC_STATE:{asymmetric_state}", "evidence": evidence})
    return {
        "status": "AVAILABLE",
        "lanes": lanes,
        "lane_counts": {lane: len(rows) for lane, rows in lanes.items()},
        "requires_private_portfolio": False,
    }


def _build_investment_accounts_section(portfolio_snapshot: Mapping[str, Any] | None) -> dict[str, Any]:
    """PRIVATE_MULTI_BROKER_INVESTMENT_ACCOUNT_CONTEXT_V1, Section 8: an aggregate-only owner
    summary (never a per-account breakdown, never a raw account alias/number -- see
    ``private_portfolio_research_handoff.py`` for the anonymized per-account form meant for
    external upload). Purely informational: nothing here is read by ``_holding_action``,
    ``_watchlist_action``, or ``_build_attention_queue`` -- cash existing is capital context, not
    a BUY signal."""
    if not isinstance(portfolio_snapshot, Mapping):
        return {"status": "PRIVATE_PORTFOLIO_NOT_SUPPLIED"}
    aggregate = portfolio_snapshot.get("investment_accounts_portfolio_context") or {}
    if aggregate.get("status") in (None, "NOT_PROVIDED"):
        return {"status": "NOT_PROVIDED", "broker_account_count": 0}
    totals = aggregate.get("totals") or {}
    return {
        "status": aggregate.get("status"),
        "broker_account_count": aggregate.get("account_count", 0),
        "broker_cash": totals.get("total_broker_cash"),
        "reserved_cash": totals.get("total_reserved_cash"),
        "receivables": totals.get("total_receivables"),
        "margin_debt": totals.get("total_margin_debt"),
        "broker_reported_nav": totals.get("total_broker_reported_nav"),
        "broker_reported_securities_market_value": totals.get("total_broker_reported_securities_market_value"),
        "as_of_consistency": aggregate.get("as_of_consistency"),
        "source_artifact_identity": aggregate.get("artifact_identity"),
    }


_QUANT_RISK_HORIZON_ORDER = ("L20", "L60", "L120", "L250")


def _build_portfolio_quant_risk_section(quant_risk_artifact: Mapping[str, Any] | None) -> dict[str, Any]:
    """PERSONAL_PORTFOLIO_QUANT_RISK_DECOMPOSITION_V1, Section 14: measurement-only owner view.

    Deliberately never consulted by ``_holding_action``, ``_watchlist_action``,
    ``_build_rotation_section``, or ``_build_attention_queue`` -- this is the whole point of the
    "measurement first" boundary: a high measured risk contribution or concentration figure never
    itself changes a BUY/SELL/HOLD label or attention-queue bucket in this milestone.
    """
    if not isinstance(quant_risk_artifact, Mapping):
        return {"status": "PRIVATE_PORTFOLIO_NOT_SUPPLIED"}
    if quant_risk_artifact.get("status") != "AVAILABLE":
        return {"status": quant_risk_artifact.get("status", "NOT_AVAILABLE"),
                "source_coverage_status": (quant_risk_artifact.get("source_coverage") or {}).get("status")}

    exposure = quant_risk_artifact.get("exposure_and_concentration") or {}
    concentration = exposure.get("concentration") or {}
    coverage_by_horizon = quant_risk_artifact.get("coverage_by_horizon") or {}
    risk_contribution_nav = (quant_risk_artifact.get("risk_contribution") or {}).get("NAV_SCALED_EQUITY_RISK") or {}
    diversification_nav = (quant_risk_artifact.get("diversification") or {}).get("NAV_SCALED_EQUITY_RISK") or {}
    sensitivity_by_horizon = quant_risk_artifact.get("sensitivity_leave_one_to_cash") or {}

    single_name_weights = {ticker: weight for ticker, weight in (exposure.get("single_name_weights") or {}).items() if weight is not None}
    top_capital_weights = sorted(single_name_weights.items(), key=lambda item: item[1], reverse=True)[:5]

    measured_horizon = next((horizon for horizon in _QUANT_RISK_HORIZON_ORDER if (risk_contribution_nav.get(horizon) or {}).get("status") == "AVAILABLE"), None)
    top_risk_contributors: list[tuple[str, float]] = []
    capital_vs_risk_gaps: list[tuple[str, float]] = []
    if measured_horizon:
        per_ticker = risk_contribution_nav[measured_horizon].get("per_ticker") or {}
        top_risk_contributors = sorted(((ticker, row["component_contribution_pct"]) for ticker, row in per_ticker.items()), key=lambda item: item[1], reverse=True)[:5]
        capital_vs_risk_gaps = sorted(((ticker, row["capital_weight_minus_risk_contribution_pct"]) for ticker, row in per_ticker.items()), key=lambda item: abs(item[1]), reverse=True)[:5]

    diversification_row = diversification_nav.get(measured_horizon) if measured_horizon else None
    largest_reduction: dict[str, Any] | None = None
    sensitivity_row = sensitivity_by_horizon.get(measured_horizon) if measured_horizon else None
    if isinstance(sensitivity_row, Mapping) and sensitivity_row.get("status") == "AVAILABLE":
        candidates = [(ticker, row["absolute_delta"]) for ticker, row in (sensitivity_row.get("per_ticker") or {}).items() if row.get("status") == "AVAILABLE"]
        if candidates:
            ticker, delta = min(candidates, key=lambda item: item[1])
            largest_reduction = {"ticker": ticker, "absolute_volatility_delta": delta}

    return {
        "status": "AVAILABLE",
        "measured_horizon": measured_horizon,
        "coverage": {
            "source_coverage_status": (quant_risk_artifact.get("source_coverage") or {}).get("status"),
            "coverage_by_horizon_status": {horizon: row.get("status") for horizon, row in coverage_by_horizon.items()},
            "unresolved_position_count": (quant_risk_artifact.get("unresolved_positions") or {}).get("count"),
        },
        "exposure": {
            "equity_exposure_to_nav": exposure.get("equity_exposure_to_nav"),
            "broker_cash_to_nav": exposure.get("broker_cash_to_nav"),
            "margin_debt_to_nav": exposure.get("margin_debt_to_nav"),
        },
        "concentration": {
            "largest_weights": top_capital_weights, "hhi": concentration.get("hhi"), "effective_positions": concentration.get("effective_n"),
        },
        "risk": {
            "top_capital_weights": top_capital_weights, "top_risk_contributors": top_risk_contributors,
            "capital_weight_vs_risk_contribution_gaps": capital_vs_risk_gaps,
        },
        "diversification": {
            "correlation_concentration_group_count": (diversification_row or {}).get("correlation_concentration_group_count"),
            "effective_n": concentration.get("effective_n"),
            "diversification_ratio": (diversification_row or {}).get("diversification_ratio"),
        },
        "sensitivities": {"largest_volatility_reduction_if_moved_to_cash": largest_reduction},
        "warnings": list(quant_risk_artifact.get("warnings") or []),
        "authority_boundary": {
            **(quant_risk_artifact.get("authority_boundary") or {}),
            "measurement_only_never_wired_into_holding_action_or_attention_queue": True,
        },
        "source_artifact_identity": quant_risk_artifact.get("artifact_identity"),
    }


def _build_rotation_section(
    *, holdings: Sequence[Mapping[str, Any]], discovery_lanes: Mapping[str, list[dict[str, Any]]],
    sector_by_ticker: Mapping[str, str],
) -> dict[str, Any]:
    """A rotation pair only ever cites already-computed posture/evidence -- never cost basis
    (never read anywhere in this function) -- and only ever pairs a CURRENT_CONFIRMED source
    (``holdings`` is already exactly that subset) with a same-sector DISCOVERY candidate, so the
    comparison is at least sector-comparable rather than an arbitrary cross-sector implication.
    A source with no same-sector destination candidate emits no pair at all -- fail closed, never
    a forced or cross-sector comparison."""
    destination_candidates: dict[str, list[dict[str, Any]]] = {}
    for lane in ("TACTICAL_SETUP", "VALUATION_DISLOCATION"):
        for row in discovery_lanes.get(lane) or []:
            destination_candidates.setdefault(row["ticker"], []).append(row)

    pairs: list[dict[str, Any]] = []
    for holding in holdings:
        if holding["action"] not in ("EXIT_REVIEW", "REDUCE_REVIEW"):
            continue
        source_ticker = holding["ticker"]
        source_sector = sector_by_ticker.get(source_ticker)
        if not source_sector:
            continue
        destinations = sorted(
            ticker for ticker in destination_candidates
            if ticker != source_ticker and sector_by_ticker.get(ticker) == source_sector
        )[:_ROTATION_DESTINATION_LIMIT]
        if not destinations:
            continue
        pairs.append({
            "source_ticker": source_ticker,
            "source_action": holding["action"],
            "source_sector": source_sector,
            "consider_reduce": source_ticker,
            "consider_candidates": [
                {"ticker": ticker, "lanes": [row["lane"] for row in destination_candidates[ticker]], "reason": destination_candidates[ticker][0]["reason"]}
                for ticker in destinations
            ],
            "reason": f"Existing holding {source_ticker}'s own research posture is {holding['portfolio_action_research']!r} "
                      f"(security posture led to {holding['action']}) while same-sector ({source_sector}) candidates above show materially stronger evidence.",
            "blockers": [
                "NOT_AN_EXECUTION_ORDER", "COST_BASIS_NOT_USED_IN_THIS_ARGUMENT",
                "DESTINATION_SIZING_STILL_SUBJECT_TO_ITS_OWN_PORTFOLIO_CONSTRAINTS",
            ],
        })
    return {"status": "AVAILABLE", "pairs": pairs, "requires_private_portfolio": True, "destination_limit_per_source": _ROTATION_DESTINATION_LIMIT}


def _build_attention_queue(*, holdings: Sequence[Mapping[str, Any]], unresolved: Sequence[Mapping[str, Any]], watchlist_entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for item in unresolved:
        rows.append({"ticker": item["ticker"], "bucket": "PORTFOLIO_DATA_REVIEW", "source_section": "UNRESOLVED_PORTFOLIO", "reason": "CURRENT_POSITION_UNRESOLVED"})
    for holding in holdings:
        action = holding["action"]
        if action in ("EXIT_REVIEW", "REDUCE_REVIEW", "ADD_CANDIDATE"):
            bucket = "ACTION_REVIEW_NOW"
        elif action == "HOLD_NO_ADD":
            bucket = "THESIS_REVIEW"
        elif action == "WAIT_FOR_CONFIRMATION":
            bucket = "CONFIRMATION_WATCH"
        else:
            bucket = "NO_ACTION_REQUIRED"
        rows.append({"ticker": holding["ticker"], "bucket": bucket, "source_section": "PORTFOLIO", "reason": action})
    for entry in watchlist_entries:
        action = entry.get("action")
        if action == "BUY_PROBE_CANDIDATE":
            bucket = "ACTION_REVIEW_NOW"
        elif action == "WAIT_FOR_CONFIRMATION":
            bucket = "CONFIRMATION_WATCH"
        else:
            bucket = "NO_ACTION_REQUIRED"
        rows.append({"ticker": entry["ticker"], "bucket": bucket, "source_section": "WATCHLIST", "reason": action})
    rows.sort(key=lambda row: (_ATTENTION_PRIORITY.get(row["bucket"], len(ATTENTION_BUCKETS)), row["ticker"]))
    counts = {bucket: sum(1 for row in rows if row["bucket"] == bucket) for bucket in ATTENTION_BUCKETS}
    return {"status": "AVAILABLE", "rows": rows, "bucket_counts": counts}


# ── Top-level artifact ─────────────────────────────────────────────────────────────────────────

def build_artifact(
    *, session: str, requested_at: str, integrated_decision_artifact: Mapping[str, Any],
    descriptive_artifact: Mapping[str, Any] | None = None, sector_leadership_artifact: Mapping[str, Any] | None = None,
    previous_descriptive_artifact: Mapping[str, Any] | None = None, previous_session: str | None = None,
    asymmetric_dislocation_artifact: Mapping[str, Any] | None = None, coverage_disposition_artifact: Mapping[str, Any] | None = None,
    owner_focus: Mapping[str, Any] | None = None, portfolio_aware_decision_artifact: Mapping[str, Any] | None = None,
    sector_by_ticker: Mapping[str, str] | None = None, excluded_tickers: frozenset[str] = frozenset(),
    portfolio_snapshot: Mapping[str, Any] | None = None, quant_risk_artifact: Mapping[str, Any] | None = None,
    opportunity_cost_input: Mapping[str, Any] | None = None,
    include_conditional_research: bool = False,
    next_session_artifact: Mapping[str, Any] | None = None,
    previous_integrated_decision_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Pure composition over already-built artifacts for one session -- no file I/O, no
    recomputation. See ``evaluate_from_retained_artifacts`` for the real-session, file-resolving
    entry point."""
    if integrated_decision_artifact.get("session") not in (None, session):
        raise ActionCenterError("INTEGRATED_DECISION_SESSION_MISMATCH")
    integrated_records = integrated_decision_artifact.get("records") or {}
    if next_session_artifact is not None and not include_conditional_research:
        raise ActionCenterError("SETUP_TRANSITION_REQUIRES_CONDITIONAL_RESEARCH")
    if include_conditional_research:
        if (integrated_decision_artifact.get("contract_version") != _integrated.CONTRACT_VERSION
                or integrated_decision_artifact.get("session") != session
                or any(integrated_decision_artifact.get(k) != v for k, v in
                       _integrated.content_identity(integrated_decision_artifact).items())):
            raise ActionCenterError("CONDITIONAL_RESEARCH_INTEGRATED_IDENTITY_OR_SESSION_MISMATCH")
        for ticker, record in integrated_records.items():
            if (record.get("ticker") != ticker or record.get("as_of_session") != session
                    or record.get("decision_identity") != _integrated.decision_identity(record)):
                raise ActionCenterError("CONDITIONAL_RESEARCH_DECISION_IDENTITY_OR_SESSION_MISMATCH")
        if coverage_disposition_artifact is not None and coverage_disposition_artifact.get("session") != session:
            raise ActionCenterError("CONDITIONAL_RESEARCH_COVERAGE_SESSION_MISMATCH")
    coverage_records = (coverage_disposition_artifact or {}).get("records") if coverage_disposition_artifact else None
    asymmetric_records = (asymmetric_dislocation_artifact or {}).get("records") or {}

    market = _build_market_section(
        session=session, descriptive=descriptive_artifact, sector_leadership=sector_leadership_artifact,
        previous_descriptive=previous_descriptive_artifact, previous_session=previous_session,
    )
    portfolio_section, unresolved_section = _build_portfolio_sections(
        session=session, integrated_records=integrated_records, portfolio_artifact=portfolio_aware_decision_artifact,
        coverage_records=coverage_records,
    )
    held_tickers = frozenset(row["ticker"] for row in portfolio_section.get("holdings") or [])
    watchlist = _build_watchlist_section(
        session=session, integrated_records=integrated_records, owner_focus=owner_focus,
        excluded_tickers=excluded_tickers, coverage_records=coverage_records,
    )
    discovery = _build_discovery_section(
        session=session, integrated_records=integrated_records, asymmetric_records=asymmetric_records,
        excluded_tickers=excluded_tickers, held_tickers=held_tickers, coverage_records=coverage_records,
    )
    if portfolio_aware_decision_artifact is not None:
        rotation = _build_rotation_section(
            holdings=portfolio_section.get("holdings") or [], discovery_lanes=discovery["lanes"],
            sector_by_ticker=sector_by_ticker or {},
        )
    else:
        rotation = {"status": "PRIVATE_PORTFOLIO_NOT_SUPPLIED", "pairs": [], "requires_private_portfolio": True}
    attention = _build_attention_queue(
        holdings=portfolio_section.get("holdings") or [], unresolved=unresolved_section.get("items") or [],
        watchlist_entries=watchlist.get("entries") or [],
    )
    investment_accounts = _build_investment_accounts_section(portfolio_snapshot)
    portfolio_quant_risk = _build_portfolio_quant_risk_section(quant_risk_artifact)
    decision_surface = _build_decision_surface_index(
        integrated_decision_artifact, portfolio_aware_decision_artifact=portfolio_aware_decision_artifact,
    )

    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "milestone": MILESTONE,
        "session": session,
        "requested_at": requested_at,
        "market": market,
        "portfolio": portfolio_section,
        "unresolved_portfolio": unresolved_section,
        "watchlist": watchlist,
        "discovery": discovery,
        "capital_rotation": rotation,
        "investment_accounts": investment_accounts,
        "portfolio_quant_risk": portfolio_quant_risk,
        "attention_queue": attention,
        "decision_surface_index": decision_surface,
        "coverage": {
            "security_denominator": len(integrated_records),
            "portfolio_supplied": portfolio_aware_decision_artifact is not None,
            "confirmed_holding_count": len(portfolio_section.get("holdings") or []),
            "unresolved_portfolio_count": len(unresolved_section.get("items") or []),
            "watchlist_count": len(watchlist.get("entries") or []),
            "rotation_pair_count": len(rotation.get("pairs") or []),
        },
        "source_artifact_identities": {
            "integrated_investment_decision_product": integrated_decision_artifact.get("artifact_identity"),
            "asymmetric_dislocation_research": (asymmetric_dislocation_artifact or {}).get("artifact_identity"),
            "portfolio_aware_decision": (portfolio_aware_decision_artifact or {}).get("artifact_identity"),
        },
        "authority_boundary": {
            "no_universal_score": True,
            "no_fabricated_probability_or_target_price": True,
            "no_execution_order": True,
            "capital_rotation_is_research_recommendation_not_execution": True,
            "unresolved_position_never_yields_buy_sell_or_rotation_source": True,
            "closed_and_excluded_positions_never_enter_active_portfolio_decisions": True,
            "pit_authority_gap_does_not_block_current_technical_or_fundamental_research": True,
            "private_local_only_never_git_dashboard_or_public_ai_handoff": True,
            "cash_availability_is_capital_context_not_a_buy_signal": True,
            "investment_account_values_never_alter_security_or_portfolio_action_computation": True,
        },
    }
    if include_conditional_research:
        # Enrich only rows selected by the existing consumer. No new discovery lane,
        # entry action, attention bucket, portfolio inference or rank is introduced.
        rows = list(portfolio_section.get("holdings") or []) + list(watchlist.get("entries") or [])
        rows += [row for lane_rows in discovery["lanes"].values() for row in lane_rows]
        for row in rows:
            row["evidence"]["conditional_research"] = _conditional_research_details(
                integrated_records[row["ticker"]], row["evidence"],
            )
            for role in ("trigger", "invalidation"):
                boundary = row["evidence"]["conditional_research"][role]
                if boundary["numeric_display_status"] != "AVAILABLE":
                    row["evidence"][role][f"{role}_level"] = None
                    row["evidence"][role][f"distance_to_{role}_pct"] = None
        body["conditional_research_presentation"] = {
            "version": "v1", "security_denominator": len(integrated_records),
            "displayed_ticker_count": len({row["ticker"] for row in rows}),
            "omission_rule": "EXISTING_WATCHLIST_HOLDINGS_DISCOVERY_SELECTION_AND_OWNER_EXCLUSIONS",
            "priority_is_research_attention_not_capital_action": True,
        }
        if next_session_artifact is not None:
            _require_setup_transition_brief(
                session=session, current_artifact=integrated_decision_artifact,
                previous_artifact=previous_integrated_decision_artifact, brief=next_session_artifact,
            )
            for row in rows:
                row["evidence"]["conditional_research"]["setup_transition"] = _setup_transition_for_ticker(
                    session=session, ticker=row["ticker"], current_artifact=integrated_decision_artifact,
                    previous_artifact=previous_integrated_decision_artifact, brief=next_session_artifact,
                )
            body["conditional_research_presentation"]["setup_transition"] = {
                "source_contract": _next_session.CONTRACT_VERSION,
                "artifact_identity": next_session_artifact.get("artifact_identity"),
                "current_session": session,
                "previous_qualified_session": next_session_artifact.get("previous_qualified_session"),
                "explanation_only": True,
            }
    if opportunity_cost_input is not None:
        from stocklookup_core.portfolio.action_center_opportunity_cost import build_view
        view = build_view(session=session, integrated_decision=integrated_decision_artifact, request=opportunity_cost_input)
        state = opportunity_cost_input.get("owner_portfolio_state") or {}
        sources = state.get("source_identities") or {}
        snapshot_identity = sources.get("portfolio_snapshot_identity") if isinstance(sources, Mapping) else None
        if portfolio_snapshot is not None and snapshot_identity != portfolio_snapshot.get("artifact_identity"):
            raise ActionCenterError("OPPORTUNITY_COST_OWNER_SNAPSHOT_MISMATCH")
        if portfolio_aware_decision_artifact is not None:
            if portfolio_aware_decision_artifact.get("session") != session:
                raise ActionCenterError("OPPORTUNITY_COST_PORTFOLIO_DECISION_SESSION_MISMATCH")
            expected_snapshot = (portfolio_aware_decision_artifact.get("source_artifact_identities") or {}).get("portfolio_state_identity")
            if not expected_snapshot or expected_snapshot != snapshot_identity:
                raise ActionCenterError("OPPORTUNITY_COST_PORTFOLIO_DECISION_SOURCE_MISMATCH")
        body["opportunity_cost_research"] = view
    return {**body, **_identity(body)}


# ── Retained-artifact resolution (read-only; no Daily run, no provider call) ──────────────────────

def _nodash(session: str) -> str:
    return session.replace("-", "")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _descriptive_artifact_path(repo_root: Path, session: str) -> Path:
    return repo_root / "operations-review" / f"market-wide-current-descriptive-research-v1-{_nodash(session)}" / "market_wide_current_descriptive_research_artifact.json"


def _sector_leadership_artifact_path(repo_root: Path, session: str) -> Path:
    return repo_root / "operations-review" / f"current-market-sector-leadership-context-v1-{_nodash(session)}" / "current_market_sector_leadership_context_artifact.json"


def _coverage_disposition_artifact_path(repo_root: Path, session: str) -> Path:
    return repo_root / "operations-review" / f"same-session-technical-coverage-recovery-v1-{_nodash(session)}" / "same_session_technical_coverage_disposition_artifact.json"


def _previous_session(repo_root: Path, session: str) -> str | None:
    """Lexicographically latest retained descriptive-research session strictly before ``session``
    -- the same sorted-glob idiom already established elsewhere in this codebase (e.g.
    ``portfolio_aware_decision.default_latest_completed_session``), never an mtime scan."""
    root = repo_root / "operations-review"
    if not root.is_dir():
        return None
    prefix = "market-wide-current-descriptive-research-v1-"
    candidates = sorted(
        entry.name[len(prefix):] for entry in root.iterdir()
        if entry.is_dir() and entry.name.startswith(prefix) and entry.name[len(prefix):] < _nodash(session)
    )
    if not candidates:
        return None
    nodash = candidates[-1]
    return f"{nodash[0:4]}-{nodash[4:6]}-{nodash[6:8]}"


def evaluate_from_retained_artifacts(
    *, repo_root: Path, session: str | None = None, portfolio_root: Path | None = None, requested_at: str,
    include_conditional_research: bool = False,
) -> dict[str, Any]:
    """One deterministic, read-only evaluation over already-retained same-session artifacts.

    Never runs Daily, never calls a provider. Raises ``FileNotFoundError`` if no completed session
    (explicit or latest) has a retained Integrated Decision artifact. A private portfolio is
    entirely optional: when ``private_portfolio_context.portfolio_status`` is not ``READY``, the
    portfolio/unresolved/rotation sections degrade to an explicit ``PRIVATE_PORTFOLIO_NOT_SUPPLIED``
    and everything else (market/watchlist/discovery/a general attention queue) is produced exactly
    the same as when a private portfolio is present.
    """
    resolved_session = session or _pad.default_latest_completed_session(repo_root)
    if not resolved_session:
        raise FileNotFoundError("NO_RETAINED_COMPLETED_INTEGRATED_DECISION_SESSION_AVAILABLE")
    integrated_decision_artifact = _pad.load_integrated_decision_artifact(repo_root, resolved_session)
    descriptive_artifact = _load_json(_descriptive_artifact_path(repo_root, resolved_session))
    sector_leadership_artifact = _load_json(_sector_leadership_artifact_path(repo_root, resolved_session))
    coverage_disposition_artifact = _load_json(_coverage_disposition_artifact_path(repo_root, resolved_session))
    previous_session = _previous_session(repo_root, resolved_session)
    previous_descriptive_artifact = _load_json(_descriptive_artifact_path(repo_root, previous_session)) if previous_session else None
    asymmetric_dislocation_artifact = _asymmetric.build_artifact(session=resolved_session, integrated_product=integrated_decision_artifact)

    try:
        owner_focus = _owner_focus.load_owner_research_focus()
    except _owner_focus.OwnerResearchFocusError:
        owner_focus = None

    governed_sector_snapshot = _pad.load_governed_sector_snapshot(repo_root)
    sector_by_ticker, _sector_sources, _snapshot_identity = _pad.resolve_sector_by_ticker(governed_sector_snapshot=governed_sector_snapshot)

    status = _private_portfolio_context.portfolio_status(portfolio_root=portfolio_root)
    portfolio_aware_decision_artifact = None
    portfolio_snapshot = None
    quant_risk_artifact = None
    excluded_tickers: frozenset[str] = frozenset()
    if status.get("status") == "READY":
        portfolio_aware_decision_artifact = _pad.evaluate_from_retained_artifacts(
            repo_root=repo_root, session=resolved_session, portfolio_root=portfolio_root, requested_at=requested_at,
        )
        portfolio_snapshot = status.get("snapshot")
        excluded_tickers = _owner_research_exclusions.excluded_ticker_set(_owner_research_exclusions.load_research_exclusions(portfolio_root))
        try:
            quant_risk_artifact = _quant.evaluate_from_retained_artifacts(
                repo_root=repo_root, portfolio_root=portfolio_root, session=resolved_session, requested_at=requested_at,
            )
        except FileNotFoundError:
            # No retained price-history snapshot for this session (or no private portfolio) --
            # degrade this one section, never the rest of the Action Center.
            quant_risk_artifact = None

    return build_artifact(
        session=resolved_session, requested_at=requested_at, integrated_decision_artifact=integrated_decision_artifact,
        descriptive_artifact=descriptive_artifact, sector_leadership_artifact=sector_leadership_artifact,
        previous_descriptive_artifact=previous_descriptive_artifact, previous_session=previous_session,
        asymmetric_dislocation_artifact=asymmetric_dislocation_artifact, coverage_disposition_artifact=coverage_disposition_artifact,
        owner_focus=owner_focus, portfolio_aware_decision_artifact=portfolio_aware_decision_artifact,
        sector_by_ticker=sector_by_ticker, excluded_tickers=excluded_tickers, portfolio_snapshot=portfolio_snapshot,
        quant_risk_artifact=quant_risk_artifact,
        include_conditional_research=include_conditional_research,
    )


def _optional_research_private_root(artifact: Mapping[str, Any], root: Path | None) -> Path:
    destination = root or default_action_center_root()
    if "opportunity_cost_research" in artifact:
        if not destination.resolve().is_relative_to(default_action_center_root().resolve()):
            raise ActionCenterError("OPPORTUNITY_COST_OUTPUT_REQUIRES_PRIVATE_ACTION_CENTER_ROOT")
        if str(artifact.get("session")) != _destination_session(artifact.get("session")):
            raise ActionCenterError("OPPORTUNITY_COST_OUTPUT_SESSION_INVALID")
        if not (destination / artifact["session"]).resolve().is_relative_to(default_action_center_root().resolve()):
            raise ActionCenterError("OPPORTUNITY_COST_OUTPUT_REQUIRES_PRIVATE_ACTION_CENTER_ROOT")
    return destination


def _destination_session(session: Any) -> str | None:
    from datetime import date
    try:
        return date.fromisoformat(session).isoformat()
    except (TypeError, ValueError):
        return None


def _optional_research_destination(artifact: Mapping[str, Any], root: Path | None, filename: str) -> Path:
    destination = _optional_research_private_root(artifact, root) / str(artifact["session"]) / filename
    if "opportunity_cost_research" in artifact and not destination.resolve().is_relative_to(default_action_center_root().resolve()):
        raise ActionCenterError("OPPORTUNITY_COST_OUTPUT_REQUIRES_PRIVATE_ACTION_CENTER_ROOT")
    return destination


def write_private_artifact(artifact: Mapping[str, Any], *, root: Path | None = None) -> Path:
    destination = _optional_research_destination(artifact, root, "personal_investment_decision_action_center_v1.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = _canon(artifact) + "\n"
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, destination)
    return destination


def public_console_summary(artifact: Mapping[str, Any], *, destination: Path | None = None, markdown_destination: Path | None = None) -> dict[str, Any]:
    """Safe CLI surface: identities/counts/status only, never a ticker or evidence value."""
    coverage = artifact.get("coverage") or {}
    return {
        "status": "ACTION_CENTER_READY",
        "milestone": MILESTONE,
        "session": artifact.get("session"),
        "personal_investment_decision_action_center_identity": artifact.get("artifact_identity"),
        "market_status": (artifact.get("market") or {}).get("status"),
        "portfolio_status": (artifact.get("portfolio") or {}).get("status"),
        "investment_accounts_status": (artifact.get("investment_accounts") or {}).get("status"),
        "portfolio_quant_risk_status": (artifact.get("portfolio_quant_risk") or {}).get("status"),
        "watchlist_status": (artifact.get("watchlist") or {}).get("status"),
        "discovery_lane_counts": (artifact.get("discovery") or {}).get("lane_counts"),
        "attention_bucket_counts": (artifact.get("attention_queue") or {}).get("bucket_counts"),
        "coverage": coverage,
        "written_to": str(destination) if destination is not None else None,
        "markdown_written_to": str(markdown_destination) if markdown_destination is not None else None,
    }


# ── Owner-readable local Markdown view ─────────────────────────────────────────────────────────

def _md_evidence_line(evidence: Mapping[str, Any]) -> str:
    freshness = evidence.get("freshness") or {}
    return (
        f"  - why: {evidence.get('why_now') or 'n/a'} _(evidence: {evidence.get('evidence_currency') or 'n/a'}; "
        f"price: {freshness.get('price_freshness', 'NOT_EVALUATED')})_"
    )


def _md_conditional_research(evidence: Mapping[str, Any]) -> list[str]:
    details = evidence.get("conditional_research")
    if not isinstance(details, Mapping):
        return []
    priority = details.get("opportunity_priority") or {}
    reconciliation = details.get("priority_posture_reconciliation") or {}
    fundamental = details.get("fundamental_synthesis") or {}
    valuation = evidence.get("valuation_context_summary") or {}
    market = evidence.get("market_sector_context") or {}
    fundamental_reasons = {key: fundamental.get(key) for key in (
        "supporting_reason_codes", "contradicting_reason_codes", "historical_reason_codes", "evidence_gap_reason_codes",
    )}
    valuation_fitness = {key: valuation.get(key) for key in (
        "status", "peer_relative_state", "unavailable_reason_codes", "limitations",
    )}
    lines = [
        _md_evidence_line(evidence),
        f"  - Setup: {evidence.get('tactical_phase')}; structure: {evidence.get('market_structure_state')}; breakout: {details.get('breakout_state_v3') or 'NOT_PROVIDED'}; watchlist entry state: {(details.get('legacy_comparison') or {}).get('legacy_entry_state') or 'NOT_PROVIDED'}.",
        f"  - Canonical posture: {evidence.get('research_action_posture')}; policy: {evidence.get('research_action_policy_version')}; reason: {evidence.get('posture_condition_class') or 'NOT_PROVIDED'}.",
        f"  - Research priority: {priority.get('research_priority_tier') or 'UNAVAILABLE'} (attention only); entry lens: {reconciliation.get('entry_action') or 'NOT_PROVIDED'}; relationship: {reconciliation.get('reason') or 'NOT_PROVIDED'}.",
    ]
    for role in ("trigger", "invalidation"):
        boundary = details.get(role) or {}
        condition = boundary.get("condition") or {}
        basis = boundary.get("price_basis") or {}
        lines.append(
            f"  - {role.capitalize()}: observed event state={boundary.get('trigger_state') if role == 'trigger' else 'NOT_EVALUATED_BY_THIS_VIEW'}; "
            f"future condition={condition.get('status') or 'NOT_RETAINED'}, "
            f"{condition.get('operator') or 'UNKNOWN_OPERATOR'} level={boundary.get(role + '_level')}; "
            f"activation={condition.get('activation_semantics') or 'NOT_RETAINED'}; "
            f"numeric display={boundary.get('numeric_display_status')}; "
            f"basis={basis.get('research_label') or basis.get('observed_price_basis') or 'UNKNOWN'}, unit={basis.get('price_unit') or 'UNKNOWN'}; "
            f"horizon={boundary.get('horizon') or 'UNKNOWN'}."
        )
        lines.append(f"    - Condition reasons: {_canon(condition.get('reason_codes') or [])}; numeric restrictions: {_canon(boundary.get('numeric_display_reason_codes') or [])}; basis limitations: {_canon(basis.get('limitations') or [])}; warning: {boundary.get('warning') or 'NOT_PROVIDED'}.")
        lines.append(f"    - Condition source: {condition.get('source_condition_identity') or 'NOT_RETAINED'}; lineage: {_canon(condition.get('source_lineage') or {})}.")
    lines.extend([
        f"  - Technical support: {_canon(details.get('technical_support') or [])}; fundamental support: {_canon(details.get('fundamental_support') or [])}.",
        f"  - Fundamentals: {evidence.get('fundamental_state')}; availability: {details.get('fundamental_evidence_availability') or 'NOT_PROVIDED'}; reasons: {_canon(fundamental_reasons)}.",
        f"  - Valuation fitness: {_canon(valuation_fitness)}; market regime: {market.get('market_regime') or 'UNKNOWN'}; sector leadership: {market.get('sector_leadership') or 'UNKNOWN'}; breadth qualification: {(market.get('market_breadth') or {}).get('status') or 'NOT_PROVIDED'}.",
        f"  - Counter-thesis: {_canon(evidence.get('counter_thesis') or [])}; uncertainties: {_canon(evidence.get('material_uncertainties') or [])}.",
        f"  - Evidence fitness and blockers: {_canon(evidence.get('evidence_axes_summary') or {})}.",
        f"  - Unavailable exact uses: {_canon(details.get('exact_capabilities_unavailable') or [])}; missing-evidence effect: {details.get('missing_evidence_decision_effect') or 'NOT_PROVIDED'}.",
        f"  - Session/as-of lineage: {_canon(details.get('evidence_currency_lineage'))}; source identities: {_canon(details.get('source_identities') or {})}; decision: {(evidence.get('source_identities') or {}).get('decision_identity')}.",
        "  - Future conditions are confirmation requirements, not observed events. Portfolio fit, sizing and execution remain separate; invalidation is analytical, not a stop-loss order.",
    ])
    transition = details.get("setup_transition")
    if isinstance(transition, Mapping):
        lines.extend(_md_setup_transition(transition))
    return lines


def _md_setup_transition(transition: Mapping[str, Any]) -> list[str]:
    lines = [
        f"  - Research-state evolution: previous session {transition.get('previous_qualified_session') or 'NONE'}; current session {transition.get('current_session') or 'UNKNOWN'}; status {transition.get('status')}.",
        f"  - Previous posture: {transition.get('previous_research_action_posture') or 'NO_PREVIOUS_RECORD'}; current canonical posture: {transition.get('current_canonical_posture') or 'UNKNOWN'}; governed transition label: {transition.get('governed_transition_label') or 'NOT_AVAILABLE'}. A transition label is not an investment outcome.",
    ]
    for key, observed in (transition.get("setup_context") or {}).items():
        if not isinstance(observed, Mapping):
            continue
        lines.append(f"  - {key}: {observed.get('status')}; previous={_canon(observed.get('previous'))}; current={_canon(observed.get('current'))}.")
    evidence = transition.get("technical_market_sector_evidence") or {}
    lines.append(
        f"  - Market direction label: {evidence.get('governed_market_direction') or 'NOT_AVAILABLE'}; sector direction label: {evidence.get('governed_sector_direction') or 'NOT_AVAILABLE'}. Market weakness is context, not a new veto."
    )
    confirmation = transition.get("tactical_confirmation") or {}
    lines.append(f"  - Tactical confirmation membership: {confirmation.get('status') or 'NOT_AVAILABLE'}. This is not a new event and not capital authorization.")
    reconciliation = transition.get("priority_posture_reconciliation") or {}
    lines.append(f"  - Priority versus posture: {reconciliation.get('reason') or 'NOT_PROVIDED'} ({reconciliation.get('reconciliation_category') or 'NOT_PROVIDED'}).")
    if transition.get("research_limitations"):
        lines.append(f"  - Research limitations: {_canon(transition.get('research_limitations'))}.")
    lines.append(f"  - Lineage: {_canon(transition.get('source_lineage') or {})}.")
    return lines


def markdown(artifact: Mapping[str, Any]) -> str:
    """Compact owner-readable render. Provenance/authority detail stays in short flags, not prose."""
    lines: list[str] = []
    session = artifact.get("session")
    lines.append(f"# Personal Investment Decision Action Center — {session}")
    lines.append("")
    lines.append(f"_Not a recommendation engine: every action below is a bounded remap of already-governed research, never a new computation._")
    lines.append("")

    lines.append("## TODAY")
    market = artifact.get("market") or {}
    if market.get("status") == "AVAILABLE":
        regime = market.get("market_regime") or {}
        lines.append(f"- Market regime: **{regime.get('current_breadth_state')}** (advance ratio {regime.get('advance_ratio')})")
        leadership = market.get("sector_leadership") or {}
        if leadership.get("leading_groups"):
            lines.append(f"- Leading sectors: {', '.join(leadership['leading_groups'])}")
        if leadership.get("lagging_or_weak_groups"):
            lines.append(f"- Lagging/weak sectors: {', '.join(leadership['lagging_or_weak_groups'])}")
        previous = market.get("previous_session_comparison") or {}
        if previous.get("status") == "AVAILABLE":
            lines.append(f"- Vs {previous.get('previous_session')}: advance-ratio delta {previous.get('advance_ratio_delta')}")
    else:
        lines.append(f"- Market: {market.get('status')} ({market.get('reason')})")
    lines.append("")

    lines.append("## PORTFOLIO ACTIONS")
    portfolio = artifact.get("portfolio") or {}
    if portfolio.get("status") == "PRIVATE_PORTFOLIO_NOT_SUPPLIED":
        if (artifact.get("opportunity_cost_research") or {}).get("status") == "AVAILABLE":
            lines.append("- The existing portfolio decision artifact was not supplied; explicit owner state is shown in optional opportunity-cost research below.")
        else:
            lines.append("- PRIVATE_PORTFOLIO_NOT_SUPPLIED — import a workbook (`portfolio import`) to enable this section.")
    elif not portfolio.get("holdings"):
        lines.append("- No confirmed current holdings.")
    else:
        for row in portfolio["holdings"]:
            lines.append(f"- **{row['ticker']}** — {row['action']} _(posture-derived; binding constraint: {row.get('binding_constraint')})_")
            lines.append(_md_evidence_line(row["evidence"]))
            lines.extend(_md_conditional_research(row["evidence"]))
    lines.append("")

    lines.append("## UNRESOLVED PORTFOLIO ITEMS")
    unresolved = artifact.get("unresolved_portfolio") or {}
    if unresolved.get("status") == "PRIVATE_PORTFOLIO_NOT_SUPPLIED":
        lines.append("- PRIVATE_PORTFOLIO_NOT_SUPPLIED")
    elif not unresolved.get("items"):
        lines.append("- None — reconciliation is clean.")
    else:
        for item in unresolved["items"]:
            lines.append(f"- **{item['ticker']}** — {item['note']}")
    lines.append("")

    lines.append("## INVESTMENT ACCOUNTS")
    accounts = artifact.get("investment_accounts") or {}
    if accounts.get("status") in ("PRIVATE_PORTFOLIO_NOT_SUPPLIED", "NOT_PROVIDED", None):
        lines.append(f"- {accounts.get('status', 'NOT_PROVIDED')} — capital context only, never a BUY/SELL signal by itself.")
    else:
        lines.append(f"- Broker accounts: {accounts.get('broker_account_count')} _(aggregate status: {accounts.get('status')})_")
        lines.append(f"- Broker cash: {accounts.get('broker_cash')}")
        lines.append(f"- Reserved cash: {accounts.get('reserved_cash')}")
        lines.append(f"- Receivables: {accounts.get('receivables')}")
        lines.append(f"- Margin debt: {accounts.get('margin_debt')}")
        lines.append(f"- Broker-reported securities market value: {accounts.get('broker_reported_securities_market_value')}")
        lines.append(f"- Broker-reported NAV: {accounts.get('broker_reported_nav')}")
        lines.append(f"- Account freshness: {accounts.get('as_of_consistency')}")
        lines.append("- Cash availability is capital context only, never a BUY/SELL signal by itself.")
    lines.append("")

    lines.append("## PORTFOLIO QUANT RISK")
    quant = artifact.get("portfolio_quant_risk") or {}
    if quant.get("status") != "AVAILABLE":
        lines.append(f"- {quant.get('status', 'NOT_AVAILABLE')} — measurement only, never affects the actions above.")
    else:
        coverage = quant.get("coverage") or {}
        exposure = quant.get("exposure") or {}
        concentration = quant.get("concentration") or {}
        risk = quant.get("risk") or {}
        diversification = quant.get("diversification") or {}
        sensitivities = quant.get("sensitivities") or {}
        lines.append(f"- Coverage: source={coverage.get('source_coverage_status')}, measured horizon={quant.get('measured_horizon')}, unresolved={coverage.get('unresolved_position_count')}")
        lines.append(f"- Equity exposure/NAV: {exposure.get('equity_exposure_to_nav')} · Cash/NAV: {exposure.get('broker_cash_to_nav')} · Margin/NAV: {exposure.get('margin_debt_to_nav')}")
        lines.append(f"- Concentration: HHI={concentration.get('hhi')}, effective positions={concentration.get('effective_positions')}")
        if concentration.get("largest_weights"):
            lines.append(f"  - Largest weights: {', '.join(f'{t}={w:.3f}' for t, w in concentration['largest_weights'])}")
        if risk.get("top_risk_contributors"):
            lines.append(f"- Top risk contributors ({quant.get('measured_horizon')}): {', '.join(f'{t}={p:.3f}' for t, p in risk['top_risk_contributors'])}")
        if risk.get("capital_weight_vs_risk_contribution_gaps"):
            lines.append(f"  - Capital-weight vs risk-weight gaps: {', '.join(f'{t}={g:+.3f}' for t, g in risk['capital_weight_vs_risk_contribution_gaps'])}")
        lines.append(f"- Diversification ratio: {diversification.get('diversification_ratio')} · Correlation clusters: {diversification.get('correlation_concentration_group_count')} · Effective N: {diversification.get('effective_n')}")
        reduction = sensitivities.get("largest_volatility_reduction_if_moved_to_cash")
        if reduction:
            lines.append(f"- Largest volatility reduction if moved to cash: {reduction['ticker']} ({reduction['absolute_volatility_delta']:+.6f})")
        lines.append("- Descriptive/research measurement only: not a BUY/SELL/REDUCE instruction.")
    lines.append("")

    lines.append("## WATCHLIST")
    watchlist = artifact.get("watchlist") or {}
    for entry in watchlist.get("entries") or []:
        tag = "★" if entry.get("owner_focus") else "-"
        lines.append(f"{tag} **{entry['ticker']}** — {entry.get('action')}")
        lines.extend(_md_conditional_research(entry["evidence"]))
    lines.append("")

    lines.append("## NEW OPPORTUNITIES")
    discovery = artifact.get("discovery") or {}
    for lane, rows in (discovery.get("lanes") or {}).items():
        if not rows:
            continue
        tickers = ", ".join(sorted({row["ticker"] for row in rows}))
        lines.append(f"- **{lane}** ({len(rows)}): {tickers}")
        for row in rows:
            if "conditional_research" in row["evidence"]:
                lines.append(f"  - **{row['ticker']}** — {row.get('reason')}")
                lines.extend(_md_conditional_research(row["evidence"]))
    lines.append("")

    lines.append("## CAPITAL ROTATION")
    rotation = artifact.get("capital_rotation") or {}
    if rotation.get("status") == "PRIVATE_PORTFOLIO_NOT_SUPPLIED":
        lines.append("- PRIVATE_PORTFOLIO_NOT_SUPPLIED")
    elif not rotation.get("pairs"):
        lines.append("- No qualifying rotation candidates today (a deteriorating holding needs a same-sector candidate with meaningfully stronger evidence).")
    else:
        for pair in rotation["pairs"]:
            destinations = ", ".join(c["ticker"] for c in pair["consider_candidates"])
            lines.append(f"- CONSIDER_REDUCE {pair['source_ticker']} → CONSIDER {destinations} _(sector: {pair['source_sector']})_")
            lines.append(f"  - {pair['reason']}")
    lines.append("")

    lines.append("## WHAT NEEDS CONFIRMATION")
    attention = artifact.get("attention_queue") or {}
    for bucket in ATTENTION_BUCKETS:
        rows = [row for row in attention.get("rows") or [] if row["bucket"] == bucket]
        if not rows:
            continue
        lines.append(f"- **{bucket}**: {', '.join(row['ticker'] for row in rows)}")
    lines.append("")

    if "opportunity_cost_research" in artifact:
        from stocklookup_core.portfolio.action_center_opportunity_cost import markdown as opportunity_markdown
        lines.extend(opportunity_markdown(artifact["opportunity_cost_research"]))

    lines.append("## DATA / AUTHORITY WARNINGS")
    lines.append(f"- Security denominator: {(artifact.get('coverage') or {}).get('security_denominator')}")
    if "conditional_research_presentation" in artifact:
        presentation = artifact["conditional_research_presentation"]
        lines.append(f"- Conditional detail coverage: {presentation['displayed_ticker_count']}/{presentation['security_denominator']}; omissions follow existing watchlist/holdings/discovery selection and owner exclusions.")
    if "opportunity_cost_research" in artifact:
        lines.append(f"- Existing portfolio decision artifact supplied: {(artifact.get('coverage') or {}).get('portfolio_supplied')}; optional owner state: {(artifact['opportunity_cost_research'].get('owner_state_status') or artifact['opportunity_cost_research']['status'])}.")
    else:
        lines.append(f"- Portfolio supplied: {(artifact.get('coverage') or {}).get('portfolio_supplied')}")
    lines.append("- No universal score, no fabricated probability/target price, no execution order anywhere in this file.")
    lines.append("")
    return "\n".join(lines)


def write_markdown(artifact: Mapping[str, Any], *, root: Path | None = None) -> Path:
    destination = _optional_research_destination(artifact, root, "personal_investment_decision_action_center.md")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(markdown(artifact), encoding="utf-8")
    return destination
