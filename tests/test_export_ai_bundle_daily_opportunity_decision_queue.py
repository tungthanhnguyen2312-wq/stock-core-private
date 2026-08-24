"""Normal-bundle tests for the retained daily opportunity-decision queue."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from daily_opportunity_decision_queue import content_identity
from export_ai_bundle import (
    DAILY_OPPORTUNITY_DECISION_QUEUE_ARTIFACT,
    attach_daily_opportunity_decision_queue,
    load_daily_opportunity_decision_queue_artifact,
)


def _retained_queue() -> dict:
    return json.loads(DAILY_OPPORTUNITY_DECISION_QUEUE_ARTIFACT.read_text(encoding="utf-8"))


def _normal_bundle(session: str = "2026-08-21") -> dict:
    return {"reference_session_date": session, "tickers": {"BKC": {}, "ACE": {}}}


def test_normal_bundle_attaches_the_exact_self_verified_queue_without_an_opt_in_flag():
    bundle = _normal_bundle()
    attach_daily_opportunity_decision_queue(bundle)
    retained = _retained_queue()
    assert bundle["daily_opportunity_decision_queue"] == retained
    assert bundle["daily_opportunity_decision_queue"]["contract_version"] == "daily_opportunity_decision_queue/v1"
    assert content_identity(bundle["daily_opportunity_decision_queue"])["artifact_sha256"] == retained["artifact_sha256"]


def test_attachment_is_deterministic_and_preserves_full_and_legacy_queue_surfaces_separately():
    first = _normal_bundle(); second = _normal_bundle()
    attach_daily_opportunity_decision_queue(first)
    attach_daily_opportunity_decision_queue(second)
    queue = first["daily_opportunity_decision_queue"]
    assert first == second
    assert queue["full_priority_now"] == _retained_queue()["full_priority_now"]
    assert queue["primary_review_candidates"] == _retained_queue()["primary_review_candidates"]
    assert queue["primary_review_candidates"]["policy_kind"] == "EXISTING_EVIDENCE_GATED_ELIGIBILITY_NOT_A_FIXED_CAP"
    assert queue["lane_queues"] == _retained_queue()["lane_queues"]
    assert queue["multi_strategy"] == _retained_queue()["multi_strategy"]


def test_missing_or_session_mismatched_queue_keeps_legacy_bundle_shape_unchanged():
    missing = _normal_bundle()
    attach_daily_opportunity_decision_queue(missing, Path("does-not-exist.json"))
    assert missing == _normal_bundle()

    mismatched = _normal_bundle("2026-08-22")
    expected = copy.deepcopy(mismatched)
    attach_daily_opportunity_decision_queue(mismatched)
    assert mismatched == expected


def test_priority_now_avoid_preserves_non_entry_action_and_authority_boundaries():
    bundle = _normal_bundle()
    attach_daily_opportunity_decision_queue(bundle)
    queue = bundle["daily_opportunity_decision_queue"]
    bkc = queue["records"]["BKC"]
    assert bkc["research_priority_tier"] == "PRIORITY_NOW"
    assert bkc["entry_action"] == "AVOID"
    assert bkc["entry_relevant"] is False
    assert bkc["is_actionable"] is False
    assert bkc["invalidation_or_context_warnings"] == _retained_queue()["records"]["BKC"]["invalidation_or_context_warnings"]
    assert queue["authority_boundary"]["research_priority_is_not_trade_readiness"] is True
    assert queue["authority_boundary"]["priority_now_is_not_sizing_ready"] is True


def test_loader_fails_closed_on_missing_artifact():
    assert load_daily_opportunity_decision_queue_artifact(Path("does-not-exist.json")) is None
