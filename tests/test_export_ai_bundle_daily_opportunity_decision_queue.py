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


def test_registered_session_resolves_its_own_queue_not_the_2026_08_24_queue():
    prior = _normal_bundle("2026-08-21")
    attach_daily_opportunity_decision_queue(prior)
    assert prior["daily_opportunity_decision_queue"]["research_session"] == "2026-08-21"
    assert prior["daily_opportunity_decision_queue"]["artifact_identity"] != _retained_queue("2026-08-24")["artifact_identity"]


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


def test_registered_priority_now_avoid_remains_avoid_in_the_prior_session_queue():
    prior = _normal_bundle("2026-08-21")
    attach_daily_opportunity_decision_queue(prior)
    bkc = prior["daily_opportunity_decision_queue"]["records"]["BKC"]
    assert bkc["research_priority_tier"] == "PRIORITY_NOW"
    assert bkc["entry_action"] == "AVOID"
    assert bkc["entry_relevant"] is False
    assert bkc["is_actionable"] is False


def test_strategy_taxonomy_and_lane_ids_are_preserved_without_report_aliases():
    queue = _retained_queue("2026-08-24")
    assert set(STRATEGY_REGISTRY) == LANES
    assert set(queue["lane_queues"]) == LANES
    assert set(queue["records"]["HWS"]["eligible_strategies"]) <= LANES
    assert not ({"VALUE_DISCOVERY", "DIVIDEND_INCOME", "CORPORATE_CATALYST", "MOMENTUM_TREND"} & set(queue["lane_queues"]))


def test_loader_fails_closed_on_missing_artifact():
    assert load_daily_opportunity_decision_queue_artifact(Path("does-not-exist.json")) is None
