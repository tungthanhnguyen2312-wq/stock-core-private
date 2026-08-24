"""Normal-bundle tests for the retained daily opportunity-decision queue."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from daily_opportunity_decision_queue import content_identity
from export_ai_bundle import (
    attach_daily_opportunity_decision_queue,
    load_daily_opportunity_decision_queue_artifact,
    resolve_daily_opportunity_decision_queue_artifact,
)
from polymorphic_current_strategy_classification import STRATEGY_REGISTRY


LANES = {
    "TREND_MOMENTUM", "BREAKOUT", "EARLY_REVERSAL", "BASE_ACCUMULATION",
    "FUNDAMENTAL_IMPROVEMENT", "EVENT_DRIVEN", "VALUE",
}


def _retained_queue(session: str) -> dict:
    resolved = resolve_daily_opportunity_decision_queue_artifact(session)
    assert resolved is not None
    return dict(resolved[0])


def _normal_bundle(session: str = "2026-08-24") -> dict:
    return {"reference_session_date": session, "tickers": {"ABT": {}, "HWS": {}}}


def test_normal_bundle_attaches_the_exact_self_verified_queue_without_an_opt_in_flag():
    bundle = _normal_bundle()
    attach_daily_opportunity_decision_queue(bundle)
    retained = _retained_queue("2026-08-24")
    assert bundle["daily_opportunity_decision_queue"] == retained
    assert bundle["daily_opportunity_decision_queue"]["contract_version"] == "daily_opportunity_decision_queue/v1"
    assert content_identity(bundle["daily_opportunity_decision_queue"])["artifact_sha256"] == retained["artifact_sha256"]


def test_resolver_uses_the_governed_same_session_registry_and_manifest_mapping():
    resolved = resolve_daily_opportunity_decision_queue_artifact("2026-08-24")
    assert resolved is not None
    queue, path = resolved
    assert path.name == "daily_opportunity_decision_queue_artifact.json"
    assert "2026-08-24" in path.parts
    assert "4c6ee6fcfc170824ac4c7ca1fb495cf7774aaebaf7d48975bd681d7e34ab80aa" in path.parts
    assert queue["research_session"] == "2026-08-24"
    assert queue["artifact_identity"] == "daily_opportunity_decision_queue:0b8158b4775cbc2b2497a61e4f98c9b0a3046350a3cdd41e727a02c42c17ab22"


def test_attachment_is_deterministic_and_preserves_full_and_legacy_queue_surfaces_separately():
    first = _normal_bundle(); second = _normal_bundle()
    attach_daily_opportunity_decision_queue(first)
    attach_daily_opportunity_decision_queue(second)
    queue = first["daily_opportunity_decision_queue"]
    assert first == second
    assert queue["full_priority_now"] == _retained_queue("2026-08-24")["full_priority_now"]
    assert queue["primary_review_candidates"] == _retained_queue("2026-08-24")["primary_review_candidates"]
    assert queue["primary_review_candidates"]["policy_kind"] == "EXISTING_EVIDENCE_GATED_ELIGIBILITY_NOT_A_FIXED_CAP"
    assert queue["lane_queues"] == _retained_queue("2026-08-24")["lane_queues"]
    assert queue["multi_strategy"] == _retained_queue("2026-08-24")["multi_strategy"]


def test_unknown_or_missing_session_keeps_legacy_bundle_shape_unchanged():
    unknown = _normal_bundle("2026-08-22")
    expected = copy.deepcopy(unknown)
    attach_daily_opportunity_decision_queue(unknown)
    assert unknown == expected
    assert resolve_daily_opportunity_decision_queue_artifact("2026-08-22") is None

    missing = {"tickers": {"ABT": {}}}
    expected = copy.deepcopy(missing)
    attach_daily_opportunity_decision_queue(missing)
    assert missing == expected


# 2026-08-21's own registered session inputs (registry["sessions"]["2026-08-21"]) never
# carried official_universe/event_context. It must never surface a queue that was actually
# built -- by a standalone, non-session-gated tool -- from the later 2026-08-24
# official_universe/event_context, even if that artifact is self-labelled research_session=2026-08-21.
def test_completed_prior_session_without_governed_manifest_lineage_resolves_no_queue():
    assert resolve_daily_opportunity_decision_queue_artifact("2026-08-21") is None
    prior = _normal_bundle("2026-08-21")
    expected = copy.deepcopy(prior)
    attach_daily_opportunity_decision_queue(prior)
    assert prior == expected
    assert "daily_opportunity_decision_queue" not in prior


def test_priority_now_wait_preserves_non_entry_action_and_authority_boundaries():
    bundle = _normal_bundle()
    attach_daily_opportunity_decision_queue(bundle)
    queue = bundle["daily_opportunity_decision_queue"]
    abt = queue["records"]["ABT"]
    assert abt["research_priority_tier"] == "PRIORITY_NOW"
    assert abt["entry_action"] == "WAIT"
    assert abt["entry_relevant"] is False
    assert abt["is_actionable"] is False
    assert abt["invalidation_or_context_warnings"] == _retained_queue("2026-08-24")["records"]["ABT"]["invalidation_or_context_warnings"]
    assert queue["authority_boundary"]["research_priority_is_not_trade_readiness"] is True
    assert queue["authority_boundary"]["priority_now_is_not_sizing_ready"] is True


# Real manifest_path/path/artifact_identity alone are not enough: the stated
# operation_identity must also match the manifest's own recomputed identity. A single
# tampered character -- the smallest possible forgery -- must be rejected.
def test_registry_entry_with_mismatched_operation_identity_fails_closed(tmp_path):
    registry_path = Path(__file__).resolve().parents[1] / "config" / "daily_research_session_input_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    entry = registry["completed_sessions"]["2026-08-24"]["output_artifacts"]["daily_opportunity_decision_queue"]
    real_identity = entry["operation_identity"]
    entry["operation_identity"] = real_identity[:-1] + ("0" if real_identity[-1] != "0" else "1")
    tampered_path = tmp_path / "registry.json"
    tampered_path.write_text(json.dumps(registry), encoding="utf-8")

    assert resolve_daily_opportunity_decision_queue_artifact("2026-08-24", tampered_path) is None
    # Sanity: the tamper -- not a path/environment issue -- caused the rejection above.
    assert resolve_daily_opportunity_decision_queue_artifact("2026-08-24", registry_path) is not None


# Neither the resolver fix nor the registry correction may touch the already-immutable
# 2026-08-21 prospective freeze or the session's own real registered inputs.
def test_2026_08_21_prospective_snapshot_and_session_registration_remain_immutable():
    registry_path = Path(__file__).resolve().parents[1] / "config" / "daily_research_session_input_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert "output_artifacts" not in registry["completed_sessions"]["2026-08-21"]
    session_inputs = registry["sessions"]["2026-08-21"]
    assert "official_universe" not in session_inputs and "event_context" not in session_inputs

    historical = (
        Path(__file__).resolve().parents[1]
        / "operations-review/current-decision-prospective-learning-v1-20260824"
        / "current_decision_prospective_snapshot_20260821.json"
    )
    snapshot = json.loads(historical.read_text(encoding="utf-8"))
    assert snapshot["snapshot_id"] == "prospective_research_snapshot:d227f98bfc0f9d79ae20ae0d686d2eab8085ecb014da3bf48345de7db3c3daf1"


def test_strategy_taxonomy_and_lane_ids_are_preserved_without_report_aliases():
    queue = _retained_queue("2026-08-24")
    assert set(STRATEGY_REGISTRY) == LANES
    assert set(queue["lane_queues"]) == LANES
    assert set(queue["records"]["HWS"]["eligible_strategies"]) <= LANES
    assert not ({"VALUE_DISCOVERY", "DIVIDEND_INCOME", "CORPORATE_CATALYST", "MOMENTUM_TREND"} & set(queue["lane_queues"]))


def test_loader_fails_closed_on_missing_artifact():
    assert load_daily_opportunity_decision_queue_artifact(Path("does-not-exist.json")) is None
