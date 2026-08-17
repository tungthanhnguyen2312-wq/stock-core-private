"""Deterministic canonical-universe tiers and append-only membership ledger.

This module consumes one explicit C.1 reconciliation artifact.  It neither
discovers a database nor fetches a provider: a later source can affect these
tiers only after entering C.1 through its own retained-input reconciliation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from atomic_io import atomic_write_json


SCHEMA_VERSION = "1.0.0"
RULE_VERSION = "canonical-universe-tiers/v1"
STORE_RELATIVE = Path("data") / "canonical_universe_tiers" / "artifacts"

INCLUDED = "INCLUDED"
EXCLUDED = "EXCLUDED"
UNKNOWN = "UNKNOWN"
NOT_APPLICABLE = "NOT_APPLICABLE"
STATES = frozenset({INCLUDED, EXCLUDED, UNKNOWN, NOT_APPLICABLE})

MASTER_OBSERVED = "MASTER_OBSERVED"
LISTED_EQUITY_CANDIDATE = "LISTED_EQUITY_CANDIDATE"
ACTIVE_UNIVERSE = "ACTIVE_UNIVERSE"
FRESH_DATA_UNIVERSE = "FRESH_DATA_UNIVERSE"
FEATURE_QUALIFIED_UNIVERSE = "FEATURE_QUALIFIED_UNIVERSE"
STRATEGY_ELIGIBLE_UNIVERSE = "STRATEGY_ELIGIBLE_UNIVERSE"
RESEARCH_QUALIFIED_UNIVERSE = "RESEARCH_QUALIFIED_UNIVERSE"
TIER_DAG = {
    MASTER_OBSERVED: (),
    LISTED_EQUITY_CANDIDATE: (MASTER_OBSERVED,),
    ACTIVE_UNIVERSE: (LISTED_EQUITY_CANDIDATE,),
    FRESH_DATA_UNIVERSE: (ACTIVE_UNIVERSE,),
    FEATURE_QUALIFIED_UNIVERSE: (FRESH_DATA_UNIVERSE,),
    STRATEGY_ELIGIBLE_UNIVERSE: (FRESH_DATA_UNIVERSE,),
    RESEARCH_QUALIFIED_UNIVERSE: (FEATURE_QUALIFIED_UNIVERSE,),
}

REASON_REGISTRY = frozenset({
    "observed_in_c1", "instrument_type_equity", "instrument_type_unknown",
    "instrument_type_not_equity", "instrument_type_etf", "instrument_type_warrant",
    "instrument_type_right", "instrument_type_bond", "instrument_type_derivative",
    "index_or_synthetic_reserved_unqualified", "listing_status_unknown",
    "listing_inactive_or_delisted", "listing_exchange_not_active", "exchange_unknown",
    "exchange_not_eligible", "missing_price", "stale_price", "price_basis_unqualified",
    "volume_basis_unqualified", "feature_missing", "feature_unqualified",
    "strategy_requirements_unmet", "research_evidence_insufficient",
})

# Aligned with dnse_instrument_universe.INSTRUMENT_CLASSES -- the only classifier authority this
# repository has. None of these five has an empirically-observed member yet (every non-EQUITY
# DNSE securityGroupId currently resolves to UNKNOWN_SECURITY_GROUP, never one of these); the
# mapping exists so the ledger's reason vocabulary is ready the day one is first observed, instead
# of collapsing every future non-equity class into one undifferentiated "instrument_type_not_equity"
# bucket. instrument_type_not_equity remains the fail-closed fallback for any class string outside
# both this table and the known equity/unknown/index buckets.
NON_EQUITY_CLASS_REASONS: dict[str, str] = {
    "ETF": "instrument_type_etf",
    "WARRANT": "instrument_type_warrant",
    "RIGHT": "instrument_type_right",
    "BOND": "instrument_type_bond",
    "DERIVATIVE": "instrument_type_derivative",
}


class CanonicalUniverseTierError(ValueError):
    """An explicit C.1 input, tier input, or ledger violates this contract."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _require_reason(reason_code: str) -> str:
    if reason_code not in REASON_REGISTRY:
        raise CanonicalUniverseTierError(f"unregistered_reason_code:{reason_code}")
    return reason_code


def _selected(candidate: Mapping[str, Any], field: str) -> Any:
    selected = candidate.get("selected_fields")
    if not isinstance(selected, Mapping):
        return None
    record = selected.get(field)
    return record.get("value") if isinstance(record, Mapping) else None


def _identity_key(provider_identities: Sequence[str]) -> str:
    """Continuity identity intentionally excludes C.1's versioned candidate id."""
    return f"provider-identity-set:{_hash(sorted(provider_identities))}"


def _validate_c1_artifact(c1_artifact: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(c1_artifact, Mapping):
        raise CanonicalUniverseTierError("c1_artifact_not_a_mapping")
    payload = {key: value for key, value in c1_artifact.items() if key not in {"content_hash", "artifact_id"}}
    content_hash = _hash(payload)
    if c1_artifact.get("content_hash") != content_hash:
        raise CanonicalUniverseTierError("c1_artifact_content_hash_invalid")
    if c1_artifact.get("artifact_id") != f"canonical-instrument-reconciliation:{content_hash}":
        raise CanonicalUniverseTierError("c1_artifact_identity_invalid")
    raw_candidates = c1_artifact.get("canonical_instrument_candidates")
    if isinstance(raw_candidates, (str, bytes)) or not isinstance(raw_candidates, Sequence):
        raise CanonicalUniverseTierError("c1_candidates_missing")
    candidates: list[dict[str, Any]] = []
    candidate_ids: set[str] = set()
    continuity_keys: set[str] = set()
    for raw in raw_candidates:
        if not isinstance(raw, Mapping):
            raise CanonicalUniverseTierError("c1_candidate_not_a_mapping")
        candidate_id = _text(raw.get("candidate_id"))
        identities = raw.get("provider_identities")
        if candidate_id is None or isinstance(identities, (str, bytes)) or not isinstance(identities, Sequence):
            raise CanonicalUniverseTierError("c1_candidate_identity_missing")
        normalized_identity_values = [_text(value) for value in identities]
        if not normalized_identity_values or any(value is None for value in normalized_identity_values):
            raise CanonicalUniverseTierError("c1_candidate_provider_identities_invalid")
        normalized_identities = sorted(set(normalized_identity_values))
        continuity_key = _identity_key(normalized_identities)  # survives a C.1 link-rule revision
        if candidate_id in candidate_ids or continuity_key in continuity_keys:
            raise CanonicalUniverseTierError("c1_candidate_identity_not_unique")
        candidate_ids.add(candidate_id)
        continuity_keys.add(continuity_key)
        candidates.append({
            "candidate_id": candidate_id,
            "instrument_identity_key": continuity_key,
            "provider_identities": normalized_identities,
            "instrument_class": _text(_selected(raw, "instrument_class")),
            "listing_status": _text(_selected(raw, "listing_status")),
            "exchange": _text(_selected(raw, "exchange")),
        })
    return sorted(candidates, key=lambda item: item["instrument_identity_key"])


def _membership(candidate: Mapping[str, Any], tier: str, state: str, reason_code: str, *, tier_scope: str | None = None,
                reason_detail: str | None = None, quality_status: str = "unqualified") -> dict[str, Any]:
    if state not in STATES:
        raise CanonicalUniverseTierError(f"invalid_state:{state}")
    _require_reason(reason_code)
    return {
        "instrument_candidate_id": candidate["candidate_id"],
        "instrument_identity_key": candidate["instrument_identity_key"],
        "provider_identities": list(candidate["provider_identities"]),
        "instrument_class": candidate["instrument_class"],
        "exchange": candidate["exchange"],
        "tier": tier,
        "tier_scope": tier_scope,
        "state": state,
        "reason_code": reason_code,
        "reason_detail": reason_detail,
        "quality_status": quality_status,
    }


def _listed_equity(candidate: Mapping[str, Any]) -> dict[str, Any]:
    instrument_class = candidate["instrument_class"]
    if instrument_class == "EQUITY":
        return _membership(candidate, LISTED_EQUITY_CANDIDATE, INCLUDED, "instrument_type_equity", quality_status="provider_reported")
    if instrument_class in {None, "UNKNOWN", "UNKNOWN_SECURITY_GROUP"}:
        return _membership(candidate, LISTED_EQUITY_CANDIDATE, UNKNOWN, "instrument_type_unknown")
    if instrument_class in {"INDEX", "SYNTHETIC", "INDEX_OR_SYNTHETIC"}:
        # Reserved/future-only: no current classifier authority (dnse_instrument_universe.
        # INSTRUMENT_CLASSES) has ever emitted any of these values, so this branch is not a proven
        # mapping -- quality_status stays the "unqualified" default rather than claiming
        # provider_reported for a classification no provider has actually reported.
        return _membership(candidate, LISTED_EQUITY_CANDIDATE, NOT_APPLICABLE, "index_or_synthetic_reserved_unqualified")
    reason_code = NON_EQUITY_CLASS_REASONS.get(instrument_class, "instrument_type_not_equity")
    return _membership(candidate, LISTED_EQUITY_CANDIDATE, EXCLUDED, reason_code, quality_status="provider_reported")


def _inherit(candidate: Mapping[str, Any], tier: str, parent: Mapping[str, Any]) -> dict[str, Any]:
    return _membership(candidate, tier, parent["state"], parent["reason_code"],
                       reason_detail=parent.get("reason_detail"), quality_status=parent["quality_status"])


def _active(candidate: Mapping[str, Any], listed: Mapping[str, Any]) -> dict[str, Any]:
    if listed["state"] != INCLUDED:
        return _inherit(candidate, ACTIVE_UNIVERSE, listed)
    listing_status = candidate["listing_status"]
    if listing_status in {"INACTIVE", "DELISTED"}:
        return _membership(candidate, ACTIVE_UNIVERSE, EXCLUDED, "listing_inactive_or_delisted", quality_status="provider_reported")
    if listing_status != "ACTIVE":
        return _membership(candidate, ACTIVE_UNIVERSE, UNKNOWN, "listing_status_unknown")
    if candidate["exchange"] is None:
        return _membership(candidate, ACTIVE_UNIVERSE, UNKNOWN, "exchange_unknown")
    return _membership(candidate, ACTIVE_UNIVERSE, INCLUDED, "observed_in_c1", quality_status="provider_reported")


def _coverage_membership(candidate: Mapping[str, Any], parent: Mapping[str, Any], tier: str,
                         coverage: Mapping[str, Mapping[str, Any]] | None) -> dict[str, Any]:
    if parent["state"] != INCLUDED:
        return _inherit(candidate, tier, parent)
    record = None if coverage is None else coverage.get(candidate["instrument_identity_key"])
    if not isinstance(record, Mapping):
        return _membership(candidate, tier, UNKNOWN, "missing_price", reason_detail="no_explicit_coverage_record")
    if record.get("price_present") is not True:
        return _membership(candidate, tier, EXCLUDED, "missing_price")
    if record.get("stale") is True:
        return _membership(candidate, tier, EXCLUDED, "stale_price")
    if record.get("price_basis_qualified") is not True:
        return _membership(candidate, tier, EXCLUDED, "price_basis_unqualified")
    if record.get("volume_basis_qualified") is not True:
        return _membership(candidate, tier, EXCLUDED, "volume_basis_unqualified")
    return _membership(candidate, tier, INCLUDED, "observed_in_c1", quality_status="explicit_coverage_input")


def _qualification_membership(candidate: Mapping[str, Any], parent: Mapping[str, Any], tier: str,
                              qualification: Mapping[str, Mapping[str, Any]] | None, *, scope: str | None = None,
                              missing_reason: str, failed_reason: str) -> dict[str, Any]:
    if parent["state"] != INCLUDED:
        inherited = _inherit(candidate, tier, parent)
        inherited["tier_scope"] = scope
        return inherited
    record = None if qualification is None else qualification.get(candidate["instrument_identity_key"])
    if not isinstance(record, Mapping):
        return _membership(candidate, tier, UNKNOWN, missing_reason, tier_scope=scope)
    if record.get("qualified") is not True:
        return _membership(candidate, tier, EXCLUDED, failed_reason, tier_scope=scope)
    return _membership(candidate, tier, INCLUDED, "observed_in_c1", tier_scope=scope, quality_status="explicit_qualification_input")


def _snapshot(*, tier: str, tier_scope: str | None, memberships: Sequence[Mapping[str, Any]], universe_version: str,
              source_c1_artifact_id: str, as_of_session: str, generated_at: str, total_count: int) -> dict[str, Any]:
    states = Counter(record["state"] for record in memberships)
    if len(memberships) != total_count or sum(states.values()) != total_count:
        raise CanonicalUniverseTierError("denominator_total_not_anchored_to_master_observed")
    excluded_by_reason = Counter(record["reason_code"] for record in memberships if record["state"] == EXCLUDED)
    unknown_by_reason = Counter(record["reason_code"] for record in memberships if record["state"] == UNKNOWN)
    return {
        "universe_tier": tier,
        "tier_scope": tier_scope,
        "universe_version": universe_version,
        "source_c1_artifact_id": source_c1_artifact_id,
        "as_of_session": as_of_session,
        "generated_at": generated_at,
        "included_count": states[INCLUDED],
        "excluded_count": states[EXCLUDED],
        "unknown_count": states[UNKNOWN],
        "not_applicable_count": states[NOT_APPLICABLE],
        "total_count": total_count,
        "excluded_by_reason": dict(sorted(excluded_by_reason.items())),
        "unknown_by_reason": dict(sorted(unknown_by_reason.items())),
        "memberships": [dict(record) for record in sorted(memberships, key=lambda item: item["instrument_identity_key"])],
    }


def _validate_prior_ledger(prior: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if prior is None:
        return []
    if not isinstance(prior, Mapping) or prior.get("artifact_kind") != "canonical_universe_tiers":
        raise CanonicalUniverseTierError("prior_ledger_not_a_canonical_universe_tier_artifact")
    events = prior.get("ledger_events")
    if isinstance(events, (str, bytes)) or not isinstance(events, Sequence) or any(not isinstance(item, Mapping) for item in events):
        raise CanonicalUniverseTierError("prior_ledger_events_invalid")
    event_ids = [item.get("ledger_event_id") for item in events]
    if len(event_ids) != len(set(event_ids)):
        raise CanonicalUniverseTierError("prior_ledger_event_ids_not_unique")
    return [dict(item) for item in events]


def _append_events(*, snapshots: Sequence[Mapping[str, Any]], prior_events: Sequence[Mapping[str, Any]],
                   source_c1_artifact_id: str, source_c1_content_hash: str, as_of_session: str,
                   generated_at: str) -> list[dict[str, Any]]:
    events = [dict(item) for item in prior_events]
    existing_ids = {item["ledger_event_id"] for item in events}
    for snapshot in snapshots:
        for membership in snapshot["memberships"]:
            event_identity = {
                "instrument_identity_key": membership["instrument_identity_key"], "tier": membership["tier"],
                "tier_scope": membership["tier_scope"], "state": membership["state"],
                "reason_code": membership["reason_code"], "effective_from": as_of_session,
                "source_c1_artifact_id": source_c1_artifact_id, "rule_version": RULE_VERSION,
            }
            event_id = f"universe-tier-event:{_hash(event_identity)}"
            if event_id in existing_ids:
                continue
            events.append({
                "ledger_event_id": event_id,
                "instrument_candidate_id": membership["instrument_candidate_id"],
                "instrument_identity_key": membership["instrument_identity_key"],
                "provider_identity": membership["provider_identities"],
                "instrument_class": membership["instrument_class"], "exchange": membership["exchange"],
                "tier": membership["tier"], "tier_scope": membership["tier_scope"],
                "state": membership["state"], "reason_code": membership["reason_code"],
                "reason_detail": membership["reason_detail"], "source_authority": "C1_PROMOTED_ARTIFACT",
                "dataset_reference": source_c1_artifact_id, "effective_from": as_of_session,
                "effective_to": None, "observed_at": generated_at, "as_of_session": as_of_session,
                "quality_status": membership["quality_status"], "rule_version": RULE_VERSION,
                "evidence_identity": {"c1_content_hash": source_c1_content_hash, "candidate_id": membership["instrument_candidate_id"]},
            })
            existing_ids.add(event_id)
    return sorted(events, key=lambda item: item["ledger_event_id"])


def build_universe_tier_artifact(
    c1_artifact: Mapping[str, Any], *, as_of_session: str, generated_at: str,
    coverage_by_identity: Mapping[str, Mapping[str, Any]] | None = None,
    feature_by_identity: Mapping[str, Mapping[str, Any]] | None = None,
    strategy_by_scope: Mapping[str, Mapping[str, Mapping[str, Any]]] | None = None,
    research_by_identity: Mapping[str, Mapping[str, Any]] | None = None,
    prior_ledger_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build every tier from explicit inputs and append unseen membership events."""
    if _text(as_of_session) is None or _text(generated_at) is None:
        raise CanonicalUniverseTierError("as_of_session_and_generated_at_are_required")
    candidates = _validate_c1_artifact(c1_artifact)
    source_id = str(c1_artifact["artifact_id"])
    source_hash = str(c1_artifact["content_hash"])
    universe_version = f"c1:{source_hash};rule:{RULE_VERSION}"
    total_count = len(candidates)

    master = [_membership(candidate, MASTER_OBSERVED, INCLUDED, "observed_in_c1", quality_status="observed") for candidate in candidates]
    listed = [_listed_equity(candidate) for candidate in candidates]
    active = [_active(candidate, listed[index]) for index, candidate in enumerate(candidates)]
    fresh = [_coverage_membership(candidate, active[index], FRESH_DATA_UNIVERSE, coverage_by_identity) for index, candidate in enumerate(candidates)]
    feature = [_qualification_membership(candidate, fresh[index], FEATURE_QUALIFIED_UNIVERSE, feature_by_identity,
                                         missing_reason="feature_missing", failed_reason="feature_unqualified") for index, candidate in enumerate(candidates)]
    research = [_qualification_membership(candidate, feature[index], RESEARCH_QUALIFIED_UNIVERSE, research_by_identity,
                                          missing_reason="research_evidence_insufficient", failed_reason="research_evidence_insufficient") for index, candidate in enumerate(candidates)]

    snapshot_specs: list[tuple[str, str | None, Sequence[Mapping[str, Any]]]] = [
        (MASTER_OBSERVED, None, master), (LISTED_EQUITY_CANDIDATE, None, listed),
        (ACTIVE_UNIVERSE, None, active), (FRESH_DATA_UNIVERSE, None, fresh),
        (FEATURE_QUALIFIED_UNIVERSE, None, feature), (RESEARCH_QUALIFIED_UNIVERSE, None, research),
    ]
    if strategy_by_scope is not None:
        if not isinstance(strategy_by_scope, Mapping):
            raise CanonicalUniverseTierError("strategy_by_scope_not_a_mapping")
        for scope, qualifications in sorted(strategy_by_scope.items()):
            scope_text = _text(scope)
            if scope_text is None:
                raise CanonicalUniverseTierError("strategy_eligibility_requires_tier_scope")
            if not isinstance(qualifications, Mapping):
                raise CanonicalUniverseTierError(f"strategy_scope_input_not_a_mapping:{scope_text}")
            rows = [_qualification_membership(candidate, fresh[index], STRATEGY_ELIGIBLE_UNIVERSE, qualifications,
                                              scope=scope_text, missing_reason="strategy_requirements_unmet",
                                              failed_reason="strategy_requirements_unmet")
                    for index, candidate in enumerate(candidates)]
            snapshot_specs.append((STRATEGY_ELIGIBLE_UNIVERSE, scope_text, rows))

    snapshots = [_snapshot(tier=tier, tier_scope=scope, memberships=rows, universe_version=universe_version,
                           source_c1_artifact_id=source_id, as_of_session=as_of_session, generated_at=generated_at,
                           total_count=total_count) for tier, scope, rows in snapshot_specs]
    prior_events = _validate_prior_ledger(prior_ledger_artifact)
    ledger_events = _append_events(snapshots=snapshots, prior_events=prior_events, source_c1_artifact_id=source_id,
                                   source_c1_content_hash=source_hash, as_of_session=as_of_session,
                                   generated_at=generated_at)
    payload = {
        "schema_version": SCHEMA_VERSION, "artifact_kind": "canonical_universe_tiers", "rule_version": RULE_VERSION,
        "source_c1_artifact_id": source_id, "source_c1_content_hash": source_hash, "universe_version": universe_version,
        "tier_dag": {tier: list(parents) for tier, parents in TIER_DAG.items()}, "snapshots": snapshots,
        "ledger_events": ledger_events,
    }
    content_hash = _hash(payload)
    return {**payload, "content_hash": content_hash, "artifact_id": f"canonical-universe-tiers:{content_hash}"}


def artifact_path(output_root: Path | str, content_hash: str) -> Path:
    return Path(output_root) / STORE_RELATIVE / f"{content_hash}.json"


def write_artifact(output_root: Path | str, artifact: Mapping[str, Any]) -> dict[str, Any]:
    expected = _hash({key: value for key, value in artifact.items() if key not in {"content_hash", "artifact_id"}})
    if artifact.get("content_hash") != expected or artifact.get("artifact_id") != f"canonical-universe-tiers:{expected}":
        raise CanonicalUniverseTierError("universe_tier_artifact_content_hash_invalid")
    path = artifact_path(output_root, expected)
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) == dict(artifact):
            return {"path": str(path), "written": False, "reason": "already_present_identical", "content_hash": expected}
        raise CanonicalUniverseTierError("content_addressed_artifact_collision")
    atomic_write_json(path, dict(artifact))
    return {"path": str(path), "written": True, "content_hash": expected}


def snapshots_comparable(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    """Consumers must not compare statistics across a different tier/version/session/scope."""
    keys = ("universe_tier", "universe_version", "as_of_session", "tier_scope")
    return all(left.get(key) == right.get(key) for key in keys)


def _load_json(path: Path, label: str) -> Mapping[str, Any]:
    if not path.is_file():
        raise CanonicalUniverseTierError(f"required_explicit_input_missing:{label}:{path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CanonicalUniverseTierError(f"explicit_input_not_valid_json:{label}:{path}") from exc
    if not isinstance(payload, Mapping):
        raise CanonicalUniverseTierError(f"explicit_input_not_a_mapping:{label}")
    return payload


def build_from_explicit_artifacts(*, c1_artifact_path: Path | str, output_root: Path | str, as_of_session: str,
                                  generated_at: str, prior_ledger_path: Path | str | None = None) -> dict[str, Any]:
    """Thin adapter with no implicit paths, database access, or provider calls."""
    c1 = _load_json(Path(c1_artifact_path), "c1_artifact")
    prior = _load_json(Path(prior_ledger_path), "prior_ledger") if prior_ledger_path is not None else None
    artifact = build_universe_tier_artifact(c1, as_of_session=as_of_session, generated_at=generated_at,
                                            prior_ledger_artifact=prior)
    return {"result": artifact, "artifact": write_artifact(output_root, artifact)}


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build canonical universe tiers from explicit C.1 artifacts only.")
    parser.add_argument("--c1-artifact", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--as-of-session", required=True)
    parser.add_argument("--generated-at", required=True)
    parser.add_argument("--prior-ledger", type=Path)
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv)
    built = build_from_explicit_artifacts(c1_artifact_path=args.c1_artifact, output_root=args.output_root,
                                          as_of_session=args.as_of_session, generated_at=args.generated_at,
                                          prior_ledger_path=args.prior_ledger)
    print(_canonical_json(built["artifact"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
