"""Shadow-only tactical reversal probe policy overlay.

`TACTICAL_REVERSAL_PROBE_POLICY_COUNTERFACTUAL_EVALUATION_V1` found that two T0-only
shadow candidates (a strict momentum-bucket subset of R8, and a two-session R8
persistence requirement) cleared every named timing/false-start/PAN-control criterion,
while a third (volume+return) did not -- it fails the false-start-rate margin against
the full R8 population it subsets and would have marked PAN's real 2026-09-09 control
episode `PROBE_ELIGIBLE`, exactly the false start it was supposed to expose.

This module wires only the two supported candidates as a read-only annotation layer
over the unchanged, already-produced `watchlist_tactical_entry_classifier` output. It
never invokes the classifier itself, never reads or alters `entry_state`/`entry_action`/
`rule_id`, and never emits a probability, target price, or sizing decision. Every
evaluator call is delegated, unmodified, to
`tactical_reversal_probe_policy_counterfactual_evaluation.evaluate_candidate` -- the
same functions the counterfactual evaluation validated -- so this layer cannot silently
drift from the evaluated policy.

Authority: SHADOW_ONLY / NOT_PRODUCTION_POLICY. A supported shadow verdict is a research
annotation, not an entry signal, and does not by itself authorize any Daily, Integrated
Decision, Portfolio, or execution behavior change.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

import tactical_reversal_probe_policy_counterfactual_evaluation as probe


CONTRACT_VERSION = "tactical_reversal_shadow_probe_policy/v1"
MILESTONE = "TACTICAL_REVERSAL_SHADOW_PROBE_POLICY_V1"
AUTHORITY_LABEL = "SHADOW_ONLY / NOT_PRODUCTION_POLICY"

ELIGIBLE_CANDIDATES = (
    "CANDIDATE_A_R8_MOMENTUM_BUCKET_SUBSET",
    "CANDIDATE_B_R8_TWO_SESSION_PERSISTENCE",
)
EXCLUDED_CANDIDATES: dict[str, str] = {
    "CANDIDATE_C_R8_VOLUME_RETURN_NO_BREAKDOWN_QUARTILE": (
        "REJECTED_BY_TACTICAL_REVERSAL_PROBE_POLICY_COUNTERFACTUAL_EVALUATION_V1: "
        "fails the T10 false-start-rate margin against the full R8 baseline (76.0% vs "
        "the required <=75.5%) and marks PAN's retained 2026-09-09 control episode "
        "PROBE_ELIGIBLE."
    ),
}

R0_RULE_ID = "R0_TECHNICAL_FEATURES_UNAVAILABLE"

NOT_EVALUABLE = "NOT_EVALUABLE"
PROBE_ELIGIBLE = "PROBE_ELIGIBLE"
NOT_PROBE_ELIGIBLE = "NOT_PROBE_ELIGIBLE"
PARTIALLY_UNEVALUABLE = "PARTIALLY_UNEVALUABLE"
UNEVALUABLE = "UNEVALUABLE"
SHADOW_DISPOSITIONS = frozenset({
    NOT_EVALUABLE, PROBE_ELIGIBLE, NOT_PROBE_ELIGIBLE, PARTIALLY_UNEVALUABLE, UNEVALUABLE,
})


class TacticalReversalShadowProbePolicyError(ValueError):
    """A precondition of this shadow overlay was not met."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def evaluate_shadow_probe(
    *, ticker: str, session: str,
    current_record: Mapping[str, Any],
    prior_record: Mapping[str, Any] | None = None,
    prior_evidence_supplied: bool = True,
) -> dict[str, Any]:
    """Annotate one already-produced, unchanged classifier record with shadow verdicts.

    ``current_record`` is exactly a value from
    ``watchlist_tactical_entry_classifier.build_artifact()["records"]`` for ``session``.
    ``prior_record`` is the same shape for the immediately adjacent prior trading
    session, if evidence for it was looked up at all (``prior_evidence_supplied``); if a
    caller never looked up a prior session, ``prior_evidence_supplied`` must be False so
    a genuine gap is never confused with "no attempt was made". Neither input is copied
    into or mutated by this function; both are only read.
    """
    if not isinstance(current_record, Mapping):
        raise TacticalReversalShadowProbePolicyError("CURRENT_CLASSIFIER_RECORD_REQUIRED")

    source_rule_id = current_record.get("rule_id")
    source_state = {
        "entry_state": current_record.get("entry_state"),
        "entry_action": current_record.get("entry_action"),
        "rule_id": source_rule_id,
    }

    if prior_record is not None:
        prior_row: dict[str, Any] | None = {"record": prior_record}
        prior_gap = False
    else:
        prior_row = None
        prior_gap = bool(prior_evidence_supplied)

    row = {"record": current_record, "prior_row": prior_row, "prior_row_gap": prior_gap}

    candidate_verdicts: dict[str, Any] = {
        name: probe.evaluate_candidate(name, row) for name in ELIGIBLE_CANDIDATES
    }
    eligible_names = [name for name, verdict in candidate_verdicts.items() if verdict["eligible"] is True]
    unevaluable_names = [name for name, verdict in candidate_verdicts.items() if verdict["eligible"] is None]

    fallback_reason: str | None = None
    if source_rule_id is None or source_rule_id == R0_RULE_ID:
        shadow_disposition = NOT_EVALUABLE
        fallback_reason = "SOURCE_CLASSIFIER_STATE_UNAVAILABLE"
    elif eligible_names:
        shadow_disposition = PROBE_ELIGIBLE
    elif unevaluable_names:
        shadow_disposition = PARTIALLY_UNEVALUABLE if len(unevaluable_names) < len(ELIGIBLE_CANDIDATES) else UNEVALUABLE
        fallback_reason = "ONE_OR_MORE_CANDIDATE_DIMENSIONS_UNEVALUABLE"
    else:
        shadow_disposition = NOT_PROBE_ELIGIBLE

    return {
        "contract_version": CONTRACT_VERSION,
        "authority": AUTHORITY_LABEL,
        "ticker": ticker,
        "trigger_session": session,
        "source_classifier_state": source_state,
        "shadow_disposition": shadow_disposition,
        "fallback_reason": fallback_reason,
        "probe_eligible_candidates": eligible_names,
        "unevaluable_candidates": unevaluable_names,
        "candidate_verdicts": candidate_verdicts,
        "excluded_candidates": dict(EXCLUDED_CANDIDATES),
        "classifier_state_unchanged": True,
        "no_probability_target_or_sizing_emitted": True,
    }


def build_shadow_artifact(
    *, session: str, current_tactical_artifact: Mapping[str, Any],
    prior_session: str | None = None, prior_tactical_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the shadow annotation artifact for every ticker in one real classifier run.

    Reads only already-produced classifier records (``current_tactical_artifact`` /
    ``prior_tactical_artifact``, each shaped like
    ``watchlist_tactical_entry_classifier.build_artifact()``'s own output); never
    invokes the classifier and never mutates either input.
    """
    current_records = current_tactical_artifact.get("records") or {}
    prior_records = (prior_tactical_artifact or {}).get("records") or {}
    prior_evidence_supplied = prior_tactical_artifact is not None

    shadow_records: dict[str, Any] = {}
    for ticker, record in current_records.items():
        shadow_records[ticker] = evaluate_shadow_probe(
            ticker=ticker, session=session, current_record=record,
            prior_record=prior_records.get(ticker), prior_evidence_supplied=prior_evidence_supplied,
        )

    disposition_counts: dict[str, int] = {}
    for record in shadow_records.values():
        disposition_counts[record["shadow_disposition"]] = disposition_counts.get(record["shadow_disposition"], 0) + 1

    artifact: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "milestone": MILESTONE,
        "authority": AUTHORITY_LABEL,
        "session": session,
        "prior_session": prior_session,
        "prior_session_evidence_supplied": prior_evidence_supplied,
        "source_classifier_artifact_identity": current_tactical_artifact.get("artifact_identity"),
        "prior_classifier_artifact_identity": (prior_tactical_artifact or {}).get("artifact_identity"),
        "eligible_candidate_policies": list(ELIGIBLE_CANDIDATES),
        "excluded_candidate_policies": dict(EXCLUDED_CANDIDATES),
        "records": shadow_records,
        "disposition_counts": disposition_counts,
        "authority_boundary": {
            "classifier_policy_changed": False,
            "classifier_invoked": False,
            "daily_modified": False,
            "daily_brief_binding_modified": False,
            "integrated_decision_modified": False,
            "portfolio_modified": False,
            "raw_as_traded": "NOT_PROMOTED",
            "historical_pit": "NOT_PROMOTED",
            "provider_or_network_calls": False,
            "database_written": False,
            "probability_or_recommendation": "NOT_EMITTED",
            "sizing_formula_introduced": False,
            "classifier_v2_queued": False,
            "shadow_only": True,
        },
    }
    artifact["artifact_sha256"] = _digest(artifact)
    artifact["artifact_identity"] = "tactical_reversal_shadow_probe_policy:" + artifact["artifact_sha256"]
    return artifact
