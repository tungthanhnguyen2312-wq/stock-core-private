"""Deterministic prospective observation/retention layer for the shadow probe policy.

``TACTICAL_REVERSAL_SHADOW_PROBE_POLICY_V1`` produced a T0-only annotation function
(``tactical_reversal_shadow_probe_policy.evaluate_shadow_probe``) but no durable record of
what it said at the time, and no mechanism to later ask "how did that call actually turn
out" without re-deciding it retroactively. This module adds exactly that: an immutable T0
observation envelope (identity-stamped, never rewritten) plus a strictly separate,
append-only future-outcome layer that matures T+5/T+10/T+20 trading-session-counted
descriptive metrics only as genuinely retained future sessions accumulate.

It is a read-only *consumer* of two things this repository already produces: the
already-produced ``watchlist_tactical_entry_classifier`` artifact for a session (never
re-invoked, never re-decided), and ``tactical_reversal_shadow_probe_policy.evaluate_shadow_probe``
itself (delegated to unmodified, so this layer cannot silently diverge from the policy it
observes). It creates no new evidence foundation, no provider/network call, and no
probability, target price, or sizing output.

Temporal boundary
------------------
``TACTICAL_REVERSAL_SHADOW_PROBE_POLICY_V1`` was checked in as commit
``d758814c73dc2bf60cfa605f4a6738e2c36ea6a7``, built and validated against retained evidence
through session ``2026-09-11``. That session -- and everything before it -- was already on
disk when the policy came into existence, so it can only ever be bootstrap/regression
material, never genuine forward validation, no matter how it is relabeled later. Every
observation's ``evidence_mode`` is a pure, permanent function of ``trigger_session`` versus
this fixed activation boundary; it is computed once, embedded in the immutable T0 envelope,
and never revisited. A second, entirely separate notion -- how far a given prospective
observation's future outcomes have matured (``PROSPECTIVE_PENDING`` /
``PROSPECTIVE_PARTIAL`` / ``PROSPECTIVE_MATURE``) -- is *never* stored on the T0 envelope;
it is computed fresh, on demand, from whatever future sessions are genuinely retained at
the time of asking (see ``observation_maturity_label``). Conflating the two would let a
later run silently rewrite what the policy knew at T0.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

import tactical_reversal_shadow_probe_policy as shadow
from tactical_reversal_probe_policy_counterfactual_evaluation import CONFIRMATION_RULE_IDS


CONTRACT_VERSION = "tactical_reversal_prospective_shadow_collection/v1"
MILESTONE = "TACTICAL_REVERSAL_PROSPECTIVE_SHADOW_COLLECTION_V1"

POLICY_ID = shadow.CONTRACT_VERSION
POLICY_CHECKPOINT_COMMIT = "d758814c73dc2bf60cfa605f4a6738e2c36ea6a7"
ACTIVATION_DATE = "2026-09-11"
AUTHORITY_LABEL = shadow.AUTHORITY_LABEL

BOOTSTRAP_NON_PROSPECTIVE = "BOOTSTRAP_NON_PROSPECTIVE"
PROSPECTIVE = "PROSPECTIVE"
PROSPECTIVE_PENDING = "PROSPECTIVE_PENDING"
PROSPECTIVE_PARTIAL = "PROSPECTIVE_PARTIAL"
PROSPECTIVE_MATURE = "PROSPECTIVE_MATURE"
EVIDENCE_MODES = frozenset({BOOTSTRAP_NON_PROSPECTIVE, PROSPECTIVE})

HORIZONS: dict[str, int] = {"T5": 5, "T10": 10, "T20": 20}
PENDING_HORIZON = "PENDING_NOT_ENOUGH_FUTURE_SESSIONS"
FIELD_NOT_RETAINED = "FIELD_NOT_RETAINED_AT_T0"
BASIS_UNEVALUABLE = "PRICE_BASIS_INCOMPATIBLE_OR_CLOSE_UNAVAILABLE"
CLOSE_PATH_SEMANTICS = "CLOSE_PATH_RESEARCH_PROXY_ONLY"

CONFIRMATION_TARGETS: dict[str, str] = {
    "first_R6": "R6_EARLY_REVERSAL_CANDIDATE",
    "first_R3": "R3_UPTREND_CONFIRMED_DEFAULT",
    "first_R2": "R2_BREAKOUT_READY_CONFIRMED",
}

TACTICAL_ARTIFACT_GLOB = "watchlist-tactical-entry-decision-v1-*/watchlist_tactical_entry_classifier_artifact.json"


class ProspectiveShadowCollectionError(ValueError):
    """A precondition of the prospective collection/retention layer was not met."""


def _canon(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def activation_boundary() -> dict[str, Any]:
    """Fixed, deterministic description of when this policy became authoritative."""
    return {
        "policy_id": POLICY_ID,
        "policy_checkpoint_commit": POLICY_CHECKPOINT_COMMIT,
        "activation_date": ACTIVATION_DATE,
        "boundary_rule": "SESSIONS_ON_OR_BEFORE_ACTIVATION_DATE_ARE_BOOTSTRAP_NON_PROSPECTIVE",
        "first_eligible_prospective_session_rule": "STRICTLY_GREATER_THAN_ACTIVATION_DATE",
    }


def evidence_mode_for_session(trigger_session: str) -> str:
    """Pure T0 function of the session string only -- never revisited after creation."""
    return BOOTSTRAP_NON_PROSPECTIVE if trigger_session <= ACTIVATION_DATE else PROSPECTIVE


# --------------------------------------------------------------------------------------
# Retained-evidence discovery.  A bounded, single-level glob over the one known artifact
# naming convention already used by tools/run_tactical_reversal_shadow_probe_policy.py --
# not a recursive operations-review/ scan.  This is how many prospective trading sessions
# have genuinely elapsed is discovered: by what the real Daily pipeline has actually
# retained, never by calendar arithmetic and never synthesized.
# --------------------------------------------------------------------------------------

def discover_retained_tactical_sessions(retained_evidence_root: Path | str) -> list[str]:
    """Sorted distinct session identifiers for every genuinely retained tactical artifact."""
    root = Path(retained_evidence_root) / "operations-review"
    sessions: set[str] = set()
    if not root.is_dir():
        return []
    for path in sorted(root.glob(TACTICAL_ARTIFACT_GLOB)):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        session = data.get("session")
        if isinstance(session, str):
            sessions.add(session)
    return sorted(sessions)


def load_tactical_artifact(retained_evidence_root: Path | str, *, session: str) -> Mapping[str, Any] | None:
    path = (
        Path(retained_evidence_root) / "operations-review"
        / f"watchlist-tactical-entry-decision-v1-{session.replace('-', '')}"
        / "watchlist_tactical_entry_classifier_artifact.json"
    )
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------------
# T0 observation.  Delegates every eligibility verdict, unmodified, to
# tactical_reversal_shadow_probe_policy.evaluate_shadow_probe -- this layer only adds
# activation-boundary/evidence-mode/price-basis/retention metadata around it.
# --------------------------------------------------------------------------------------

def price_basis_identity_for_artifact(tactical_artifact: Mapping[str, Any]) -> str | None:
    """A stable basis-method label, derived (not invented) from the retained artifact.

    The classifier artifact does not carry an explicit ``price_basis_identity`` field, but
    ``source_artifacts.descriptive`` is always ``"<contract_name>:<content_hash>"`` -- the
    contract-name prefix is a stable method label that is identical across sessions unless
    the production descriptive pipeline itself changes method (a genuine, detectable
    regime change). Using content-hash equality instead would make every cross-session
    comparison spuriously incompatible, since the hash differs whenever any price differs.
    """
    descriptive = (tactical_artifact.get("source_artifacts") or {}).get("descriptive")
    if not isinstance(descriptive, str) or ":" not in descriptive:
        return None
    prefix = descriptive.split(":", 1)[0]
    return prefix or None


def _trigger_price(record: Mapping[str, Any], basis_identity: str | None) -> dict[str, Any] | None:
    close = (record.get("signals") or {}).get("close")
    if not isinstance(close, (int, float)) or basis_identity is None:
        return None
    return {"close": close, "price_basis_identity": basis_identity}


def _classifier_state(record: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(record, Mapping):
        return None
    return {
        "entry_state": record.get("entry_state"),
        "entry_action": record.get("entry_action"),
        "rule_id": record.get("rule_id"),
    }


def build_prospective_observation(
    *, ticker: str, trigger_session: str,
    current_tactical_artifact: Mapping[str, Any],
    prior_session: str | None = None,
    prior_tactical_artifact: Mapping[str, Any] | None = None,
    prior_evidence_supplied: bool = True,
    retained_at: str | None = None,
) -> dict[str, Any]:
    """Build one immutable T0 prospective-shadow observation for one ticker/session.

    ``current_tactical_artifact`` and ``prior_tactical_artifact`` are exactly
    ``watchlist_tactical_entry_classifier.build_artifact()``-shaped (or the real retained
    on-disk equivalent); neither is mutated. ``retained_at`` is an optional caller-supplied
    deterministic knowledge timestamp/session marker -- never ``datetime.now()`` -- so a
    rerun with identical arguments always produces an identical observation identity.
    """
    records = current_tactical_artifact.get("records") or {}
    if ticker not in records:
        raise ProspectiveShadowCollectionError("TICKER_NOT_IN_CURRENT_TACTICAL_ARTIFACT")
    current_record = records[ticker]
    prior_record = None
    if prior_tactical_artifact is not None:
        prior_record = (prior_tactical_artifact.get("records") or {}).get(ticker)

    shadow_probe = shadow.evaluate_shadow_probe(
        ticker=ticker, session=trigger_session, current_record=current_record,
        prior_record=prior_record, prior_evidence_supplied=prior_evidence_supplied,
    )
    basis_identity = price_basis_identity_for_artifact(current_tactical_artifact)

    body: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION,
        "milestone": MILESTONE,
        "record_type": "IMMUTABLE_T0_PROSPECTIVE_SHADOW_OBSERVATION",
        "ticker": ticker,
        "trigger_session": trigger_session,
        "activation_boundary": activation_boundary(),
        "evidence_mode": evidence_mode_for_session(trigger_session),
        "retained_at": retained_at,
        "source_evidence_basis_identity": current_tactical_artifact.get("artifact_identity"),
        "source_classifier_state": _classifier_state(current_record),
        "source_production_action": current_record.get("entry_action"),
        "source_rule_id": current_record.get("rule_id"),
        "prior_trigger_session": prior_session,
        "prior_evidence_supplied": prior_evidence_supplied,
        "prior_source_evidence_basis_identity": (prior_tactical_artifact or {}).get("artifact_identity"),
        "prior_source_classifier_state": _classifier_state(prior_record),
        "candidate_a": dict(shadow_probe["candidate_verdicts"]["CANDIDATE_A_R8_MOMENTUM_BUCKET_SUBSET"]),
        "candidate_b": dict(shadow_probe["candidate_verdicts"]["CANDIDATE_B_R8_TWO_SESSION_PERSISTENCE"]),
        "shadow_disposition": shadow_probe["shadow_disposition"],
        "shadow_probe_authority": shadow_probe["authority"],
        "excluded_candidates": dict(shadow_probe["excluded_candidates"]),
        "trigger_price": _trigger_price(current_record, basis_identity),
        "authority": AUTHORITY_LABEL,
        "no_probability_target_or_sizing_emitted": True,
        "collection_boundary": {
            "classifier_invoked": False,
            "classifier_policy_changed": False,
            "production_daily_modified": False,
            "production_daily_brief_modified": False,
            "integrated_decision_modified": False,
            "portfolio_modified": False,
            "provider_or_network_call": False,
            "runtime_database_write": False,
        },
    }
    body["observation_id"] = "tactical_prospective_shadow_observation:" + _hash(body)
    return body


def observation_identity_valid(observation: Mapping[str, Any]) -> bool:
    body = dict(observation)
    observation_id = body.pop("observation_id", None)
    return observation_id == "tactical_prospective_shadow_observation:" + _hash(body)


# --------------------------------------------------------------------------------------
# Immutable retention: write-once T0 envelopes, append-only outcome-update events keyed by
# (observation_id, evaluation_as_of_session). Mirrors the write-once/content-addressed
# convention already established by durable_prospective_research_case_store.py, scoped to
# this milestone's genuinely different contract shape (tactical shadow eligibility, not an
# AI-drafted/human-reviewed investment thesis) rather than forcing an ill-fitting reuse.
# --------------------------------------------------------------------------------------

class ProspectiveShadowObservationStore:
    """One-writer, append-only local store. The caller chooses an explicit root."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()
        self.observations_dir = self.root / "observations"
        self.outcomes_dir = self.root / "outcome_updates"
        self.observations_dir.mkdir(parents=True, exist_ok=True)
        self.outcomes_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _path_for(key: str, directory: Path) -> Path:
        return directory / (hashlib.sha256(key.encode("utf-8")).hexdigest() + ".json")

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProspectiveShadowCollectionError("STORE_RECORD_UNREADABLE_OR_TAMPERED") from exc
        if not isinstance(value, dict):
            raise ProspectiveShadowCollectionError("STORE_RECORD_NOT_OBJECT")
        return value

    @staticmethod
    def _write_new_json(path: Path, payload: Mapping[str, Any]) -> None:
        data = (_canon(payload) + "\n").encode("utf-8")
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            return
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            path.unlink(missing_ok=True)
            raise

    def persist_observation(self, observation: Mapping[str, Any]) -> dict[str, Any]:
        """Idempotently persist one immutable T0 observation.

        A rerun with byte-identical content is a no-op success (same observation_id, same
        file). Any attempt to persist a *different* body under an already-used
        observation_id is impossible by construction (the id is a content hash of the
        body), so the only failure mode this guards is genuine on-disk tampering, which
        ``load_observation`` detects on read.
        """
        if not observation_identity_valid(observation):
            raise ProspectiveShadowCollectionError("OBSERVATION_CONTENT_IDENTITY_INVALID")
        path = self._path_for(observation["observation_id"], self.observations_dir)
        self._write_new_json(path, observation)
        return self.load_observation(observation["observation_id"])

    def load_observation(self, observation_id: str) -> dict[str, Any]:
        path = self._path_for(observation_id, self.observations_dir)
        if not path.exists():
            raise ProspectiveShadowCollectionError("OBSERVATION_NOT_FOUND")
        observation = self._read_json(path)
        if not observation_identity_valid(observation) or observation.get("observation_id") != observation_id:
            raise ProspectiveShadowCollectionError("OBSERVATION_CONTENT_IDENTITY_INVALID")
        return observation

    def list_observation_ids(self) -> list[str]:
        ids = []
        for path in sorted(self.observations_dir.glob("*.json")):
            raw = self._read_json(path).get("observation_id")
            if isinstance(raw, str):
                self.load_observation(raw)
                ids.append(raw)
        return sorted(set(ids))

    def persist_outcome_update(self, observation_id: str, outcome: Mapping[str, Any]) -> dict[str, Any]:
        """Idempotently append one content-addressed outcome snapshot for a session."""
        self.load_observation(observation_id)  # fail closed if the T0 envelope is missing/invalid
        if outcome.get("observation_id") != observation_id:
            raise ProspectiveShadowCollectionError("OUTCOME_OBSERVATION_ID_MISMATCH")
        path = self._path_for(outcome["outcome_update_id"], self.outcomes_dir)
        self._write_new_json(path, outcome)
        return self._read_json(path)

    def load_outcome_updates(self, observation_id: str) -> list[dict[str, Any]]:
        rows = []
        for path in sorted(self.outcomes_dir.glob("*.json")):
            event = self._read_json(path)
            if event.get("observation_id") == observation_id:
                rows.append(event)
        return sorted(rows, key=lambda item: str(item.get("evaluation_as_of_session")))

    def latest_outcome_update(self, observation_id: str) -> dict[str, Any] | None:
        updates = self.load_outcome_updates(observation_id)
        return updates[-1] if updates else None


# --------------------------------------------------------------------------------------
# Future-outcome maturity.  Every horizon is counted in genuinely retained trading
# sessions, never calendar days and never imputed. ``future_rows`` must already be
# filtered/sorted ascending to sessions strictly after trigger_session by the caller
# (``mature_outcome`` re-validates this defensively).
# --------------------------------------------------------------------------------------

def _future_row_close(row: Mapping[str, Any]) -> float | None:
    record = row.get("record")
    if not isinstance(record, Mapping):
        return None
    value = (record.get("signals") or {}).get("close")
    return value if isinstance(value, (int, float)) else None


def _basis_compatible(trigger_price: Mapping[str, Any] | None, row: Mapping[str, Any]) -> bool:
    return bool(
        trigger_price and row.get("price_basis_identity") and
        row["price_basis_identity"] == trigger_price.get("price_basis_identity") and
        _future_row_close(row) is not None
    )


def _horizon_result(name: str, count: int, trigger_price: Mapping[str, Any] | None, future_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    base = {"horizon": name, "required_future_trading_sessions": count, "status": None,
            "horizon_session": None, "available_future_sessions": len(future_rows)}
    if trigger_price is None:
        base["status"] = FIELD_NOT_RETAINED
        return base
    window = future_rows[:count]
    if len(window) < count:
        base["status"] = PENDING_HORIZON
        return base
    if not all(_basis_compatible(trigger_price, row) for row in window):
        base["status"] = BASIS_UNEVALUABLE
        return base
    trigger_close = trigger_price["close"]
    closes = [_future_row_close(row) for row in window]
    returns = [(close - trigger_close) / trigger_close for close in closes]
    first_lower_low = next((index + 1 for index, close in enumerate(closes) if close < trigger_close), None)
    base.update(
        status="MATURE",
        horizon_session=window[-1]["session"],
        return_pct=returns[-1],
        mae_pct=min(returns),
        mfe_pct=max(returns),
        lower_low_within_horizon=any(close < trigger_close for close in closes),
        sessions_to_first_lower_low=first_lower_low,
        semantics=CLOSE_PATH_SEMANTICS,
    )
    return base


def _first_transition(future_rows: Sequence[Mapping[str, Any]], rule_id: str) -> dict[str, Any]:
    for offset, row in enumerate(future_rows, start=1):
        record = row.get("record")
        if isinstance(record, Mapping) and record.get("rule_id") == rule_id:
            return {"status": "COMPLETE", "session": row["session"], "sessions_to_event": offset, "rule_id": rule_id}
    return {"status": "PENDING", "session": None, "sessions_to_event": None, "rule_id": rule_id}


def _first_confirmation(transitions: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    complete = [item for item in transitions.values() if item["status"] == "COMPLETE"]
    if not complete:
        return {"status": "PENDING", "session": None, "sessions_to_event": None, "rule_id": None}
    winner = min(complete, key=lambda item: item["sessions_to_event"])
    return dict(winner, status="COMPLETE")


def mature_outcome(
    observation: Mapping[str, Any], future_rows: Sequence[Mapping[str, Any]], *, evaluation_as_of_session: str,
) -> dict[str, Any]:
    """Compute the current outcome snapshot for one T0 observation.

    ``future_rows`` items are ``{"session", "record" (or None), "price_basis_identity"}``,
    one per genuinely retained trading session strictly after ``trigger_session`` -- a
    session with no record for this ticker (e.g. a data gap) still occupies its slot in the
    session count, since horizon counting is in trading sessions, not per-ticker rows.
    Never fabricates a session that was not actually retained.
    """
    trigger_session = observation["trigger_session"]
    if not observation_identity_valid(observation):
        raise ProspectiveShadowCollectionError("OBSERVATION_CONTENT_IDENTITY_INVALID")
    ordered = sorted(
        (row for row in future_rows if row["session"] > trigger_session),
        key=lambda row: row["session"],
    )
    ordered = [row for row in ordered if row["session"] <= evaluation_as_of_session]
    trigger_price = observation.get("trigger_price")

    horizons = {name: _horizon_result(name, count, trigger_price, ordered) for name, count in HORIZONS.items()}
    transitions = {label: _first_transition(ordered, rule_id) for label, rule_id in CONFIRMATION_TARGETS.items()}
    first_confirmation = _first_confirmation(transitions)

    outcome: dict[str, Any] = {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION + "/outcome",
        "observation_id": observation["observation_id"],
        "ticker": observation["ticker"],
        "trigger_session": trigger_session,
        "evaluation_as_of_session": evaluation_as_of_session,
        "retained_future_session_count": len(ordered),
        "horizons": horizons,
        "confirmation_transitions": transitions,
        "first_confirmation": first_confirmation,
        "no_probability_target_or_sizing_emitted": True,
        "authority_boundary": {
            "original_t0_observation_immutable": True,
            "outcomes_append_only": True,
            "no_future_bar_before_availability": True,
            "no_imputed_sessions": True,
            "close_path_is_not_intraday_mfe_mae": True,
        },
    }
    outcome["outcome_update_id"] = "tactical_prospective_shadow_outcome:" + _hash(outcome)
    return outcome


def observation_maturity_label(observation: Mapping[str, Any], outcome: Mapping[str, Any] | None) -> str:
    """Freshly-computed maturity label -- never persisted onto the T0 observation."""
    if observation["evidence_mode"] == BOOTSTRAP_NON_PROSPECTIVE:
        return BOOTSTRAP_NON_PROSPECTIVE
    if outcome is None:
        return PROSPECTIVE_PENDING
    statuses = [outcome["horizons"][name]["status"] for name in HORIZONS]
    if all(status == "MATURE" for status in statuses):
        return PROSPECTIVE_MATURE
    if any(status == "MATURE" for status in statuses):
        return PROSPECTIVE_PARTIAL
    return PROSPECTIVE_PENDING


# --------------------------------------------------------------------------------------
# Aggregate collection status.  Descriptive only -- no promotion decision, no blended
# score, Candidate C never reappears (ELIGIBLE_CANDIDATES in the shadow module structurally
# excludes it, so no candidate_c field can ever exist on an observation to aggregate).
# --------------------------------------------------------------------------------------

def _cohort_key(observation: Mapping[str, Any]) -> str:
    is_r8 = observation["source_rule_id"] == "R8_SELLING_PRESSURE_EASING"
    if not is_r8:
        return "NOT_R8_CONTROL_POPULATION"
    a = observation["candidate_a"]["eligible"] is True
    b = observation["candidate_b"]["eligible"] is True
    if a and b:
        return "A_AND_B"
    if a:
        return "A_ONLY"
    if b:
        return "B_ONLY"
    return "R8_NEITHER"


def build_collection_status(
    observations: Sequence[Mapping[str, Any]], outcomes_by_observation_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    bootstrap = [item for item in observations if item["evidence_mode"] == BOOTSTRAP_NON_PROSPECTIVE]
    prospective = [item for item in observations if item["evidence_mode"] == PROSPECTIVE]

    def _cohort_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
        counts = {"A_ONLY": 0, "B_ONLY": 0, "A_AND_B": 0, "R8_NEITHER": 0, "NOT_R8_CONTROL_POPULATION": 0}
        for row in rows:
            counts[_cohort_key(row)] += 1
        return counts

    def _horizon_maturity(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
        tally: dict[str, dict[str, int]] = {name: {"MATURE": 0, "PENDING": 0, "UNEVALUABLE": 0} for name in HORIZONS}
        for row in rows:
            outcome = outcomes_by_observation_id.get(row["observation_id"])
            for name in HORIZONS:
                if outcome is None:
                    tally[name]["PENDING"] += 1
                    continue
                status = outcome["horizons"][name]["status"]
                if status == "MATURE":
                    tally[name]["MATURE"] += 1
                elif status == PENDING_HORIZON:
                    tally[name]["PENDING"] += 1
                else:
                    tally[name]["UNEVALUABLE"] += 1
        return tally

    maturity_labels: dict[str, int] = {PROSPECTIVE_PENDING: 0, PROSPECTIVE_PARTIAL: 0, PROSPECTIVE_MATURE: 0}
    for row in prospective:
        label = observation_maturity_label(row, outcomes_by_observation_id.get(row["observation_id"]))
        maturity_labels[label] = maturity_labels.get(label, 0) + 1

    overall = "NO_PROSPECTIVE_OBSERVATIONS_YET" if not prospective else (
        "ACTIVE_COLLECTION_NO_MATURE_PROSPECTIVE_HORIZON_YET" if maturity_labels[PROSPECTIVE_MATURE] == 0
        else "ACTIVE_COLLECTION_PARTIAL_MATURITY"
    )

    return {
        "schema_version": "1.0.0",
        "contract_version": CONTRACT_VERSION + "/collection_status",
        "activation_boundary": activation_boundary(),
        "overall_status": overall,
        "bootstrap_observation_count": len(bootstrap),
        "prospective_observation_count": len(prospective),
        "prospective_cohorts": _cohort_counts(prospective),
        "bootstrap_cohorts_regression_only": _cohort_counts(bootstrap),
        "prospective_horizon_maturity": _horizon_maturity(prospective),
        "prospective_maturity_labels": maturity_labels,
        "excluded_candidates": dict(shadow.EXCLUDED_CANDIDATES),
        "authority_boundary": {
            "bootstrap_excluded_from_prospective_aggregate": True,
            "promotion_decision": "NOT_MADE_THIS_MILESTONE",
            "classifier_v2_queued": False,
            "probability_or_recommendation": "NOT_EMITTED",
        },
    }
