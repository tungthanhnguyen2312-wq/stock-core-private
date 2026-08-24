"""Adversarial proofs for DAILY_SESSION_TEMPORAL_INPUT_LOCK_HARDENING_V1."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from daily_research_session_operations import (
    _identity,
    assert_inputs_match_registered_session,
    assert_manifest_and_queue_match_registered_session,
    build_operation,
    load_registry,
    resolve_inputs,
)
from export_ai_bundle import (
    attach_daily_opportunity_decision_queue,
    resolve_daily_opportunity_decision_queue_artifact,
)
from tools.run_opportunity_decision_prospective_freeze import resolve as resolve_opportunity_freeze


ROOT = Path(__file__).resolve().parents[1]
MIXED_QUEUE = (
    ROOT / "operations-review/daily-opportunity-decision-queue-v1-20260824"
    / "daily_opportunity_decision_queue_artifact.json"
)
GOVERNED_MANIFEST = (
    ROOT / "operations-review/daily-research-session-operations-v1/2026-08-24"
    / "4c6ee6fcfc170824ac4c7ca1fb495cf7774aaebaf7d48975bd681d7e34ab80aa"
    / "run_manifest.json"
)
HISTORICAL_FREEZE = (
    ROOT / "operations-review/current-decision-prospective-learning-v1-20260824"
    / "current_decision_prospective_snapshot_20260821.json"
)
PROTECTED_FREEZE_ID = "prospective_research_snapshot:d227f98bfc0f9d79ae20ae0d686d2eab8085ecb014da3bf48345de7db3c3daf1"


def _registry() -> dict:
    return json.loads((ROOT / "config" / "daily_research_session_input_registry.json").read_text(encoding="utf-8"))


def _consistent_mixed_manifest(*, include_later_optional: bool = True) -> tuple[dict, dict]:
    manifest = json.loads(GOVERNED_MANIFEST.read_text(encoding="utf-8"))
    queue = json.loads(MIXED_QUEUE.read_text(encoding="utf-8"))
    registry = _registry()
    manifest["market_session"] = "2026-08-21"
    manifest["outputs"]["daily_opportunity_decision_queue"] = queue["artifact_identity"]
    if include_later_optional:
        pass
    else:
        artifacts = dict(manifest.get("input_artifacts") or {})
        artifacts.pop("official_universe", None)
        artifacts.pop("event_context", None)
        flow = registry["sessions"]["2026-08-21"]["market_flow_positioning"]
        artifacts["market_flow_positioning"] = {
            "artifact_identity": flow["artifact_identity"],
            "contract_version": "current_market_flow_positioning/v1",
            "freshness_state": "CURRENT_SESSION_COHERENT",
            "session": "2026-08-21",
        }
        manifest["input_artifacts"] = artifacts
    manifest.pop("operation_identity", None)
    manifest["operation_identity"] = _identity(manifest)
    assert _identity(manifest) == manifest["operation_identity"]
    return manifest, queue


def test_valid_registered_same_session_operation_and_queue_remain_governed():
    registry = load_registry(ROOT)
    inputs, _ = resolve_inputs(ROOT, "2026-08-24", registry)
    assert_inputs_match_registered_session("2026-08-24", inputs, registry)
    resolved = resolve_daily_opportunity_decision_queue_artifact("2026-08-24")
    assert resolved is not None
    queue, path = resolved
    assert queue["research_session"] == "2026-08-24"
    assert "4c6ee6fcfc170824ac4c7ca1fb495cf7774aaebaf7d48975bd681d7e34ab80aa" in path.parts
    bundle = {"reference_session_date": "2026-08-24"}
    attach_daily_opportunity_decision_queue(bundle)
    assert bundle["daily_opportunity_decision_queue"]["artifact_identity"] == queue["artifact_identity"]
    freeze, _ = resolve_opportunity_freeze("2026-08-24")
    assert freeze["research_session"] == "2026-08-24"


def test_optional_input_absent_in_session_cannot_be_injected_later():
    registry = load_registry(ROOT)
    inputs, _ = resolve_inputs(ROOT, "2026-08-21", registry)
    assert "official_universe" not in inputs and "event_context" not in inputs
    later = json.loads((ROOT / "operations-review/current-official-market-universe-integration-v1-20260824/current_official_market_universe_artifact.json").read_text(encoding="utf-8"))
    event = json.loads((ROOT / "operations-review/current-official-event-context-integration-v1-20260824/current_official_event_context_artifact.json").read_text(encoding="utf-8"))
    injected = dict(inputs)
    injected["official_universe"] = later
    injected["event_context"] = event
    with pytest.raises(ValueError, match="SESSION_INPUT_NOT_REGISTERED"):
        assert_inputs_match_registered_session("2026-08-21", injected, registry)
    with pytest.raises(ValueError, match="SESSION_INPUT_NOT_REGISTERED"):
        build_operation(injected, "2026-08-21", producer_head="producer", consumer_head="consumer", registry=registry)


def test_mixed_later_identities_fail_closed_even_with_internally_consistent_manifest(tmp_path):
    wrapped, queue = _consistent_mixed_manifest(include_later_optional=True)
    assert wrapped["market_session"] == "2026-08-21"
    assert wrapped["operation_identity"] == _identity(wrapped)
    assert (wrapped.get("outputs") or {}).get("daily_opportunity_decision_queue") == queue["artifact_identity"]
    assert queue["research_session"] == "2026-08-21"
    with pytest.raises(ValueError, match="SESSION_MANIFEST_OPTIONAL_INPUT_MISMATCH"):
        assert_manifest_and_queue_match_registered_session("2026-08-21", wrapped, queue, _registry())

    stripped, queue = _consistent_mixed_manifest(include_later_optional=False)
    with pytest.raises(ValueError, match="SESSION_QUEUE_REQUIRES_REGISTERED_OFFICIAL_UNIVERSE_AND_EVENT_CONTEXT"):
        assert_manifest_and_queue_match_registered_session("2026-08-21", stripped, queue, _registry())

    manifest_path = tmp_path / "run_manifest.json"
    manifest_path.write_text(json.dumps(wrapped), encoding="utf-8")
    registry = _registry()
    registry["completed_sessions"]["2026-08-21"]["output_artifacts"] = {
        "daily_opportunity_decision_queue": {
            "path": "operations-review/daily-opportunity-decision-queue-v1-20260824/daily_opportunity_decision_queue_artifact.json",
            "artifact_identity": queue["artifact_identity"],
            "manifest_path": str(manifest_path),
            "operation_identity": wrapped["operation_identity"],
        }
    }
    tampered = tmp_path / "registry.json"
    tampered.write_text(json.dumps(registry), encoding="utf-8")
    assert resolve_daily_opportunity_decision_queue_artifact("2026-08-21", tampered) is None
    prior = {"reference_session_date": "2026-08-21"}
    attach_daily_opportunity_decision_queue(prior, tampered)
    assert "daily_opportunity_decision_queue" not in prior


def test_completed_frozen_session_input_mutation_is_rejected():
    registry = _registry()
    registry["sessions"]["2026-08-21"]["official_universe"] = copy.deepcopy(
        registry["sessions"]["2026-08-24"]["official_universe"]
    )
    registry["sessions"]["2026-08-21"]["event_context"] = copy.deepcopy(
        registry["sessions"]["2026-08-24"]["event_context"]
    )
    with pytest.raises(ValueError, match="COMPLETED_SESSION_INPUT_MUTATION_REJECTED"):
        resolve_inputs(ROOT, "2026-08-21", registry)

    identity_swap = _registry()
    identity_swap["sessions"]["2026-08-21"]["descriptive"]["artifact_identity"] = (
        identity_swap["sessions"]["2026-08-24"]["descriptive"]["artifact_identity"]
    )
    with pytest.raises(ValueError, match="COMPLETED_SESSION_INPUT_MUTATION_REJECTED"):
        resolve_inputs(ROOT, "2026-08-21", identity_swap)

    assert resolve_daily_opportunity_decision_queue_artifact("2026-08-21") is None


def test_unknown_or_mismatched_session_fails_closed():
    with pytest.raises(ValueError, match="SESSION_NOT_REGISTERED_EXPLICIT_INPUT_MANIFEST_REQUIRED"):
        resolve_inputs(ROOT, "2026-08-22", load_registry(ROOT))
    assert resolve_daily_opportunity_decision_queue_artifact("2026-08-22") is None
    unknown = {"reference_session_date": "2026-08-22"}
    attach_daily_opportunity_decision_queue(unknown)
    assert unknown == {"reference_session_date": "2026-08-22"}
    with pytest.raises(ValueError, match="OPPORTUNITY_DECISION_FREEZE_COMPLETED_SESSION_MAPPING_MISSING"):
        resolve_opportunity_freeze("2026-08-22")


def test_immutable_2026_08_21_freeze_identity_remains_unchanged():
    before = HISTORICAL_FREEZE.read_bytes()
    snapshot = json.loads(before)
    assert snapshot["snapshot_id"] == PROTECTED_FREEZE_ID
    registry = load_registry(ROOT)
    assert "output_artifacts" not in registry["completed_sessions"]["2026-08-21"]
    assert "official_universe" not in registry["sessions"]["2026-08-21"]
    assert "event_context" not in registry["sessions"]["2026-08-21"]
    assert "official_universe" not in registry["completed_sessions"]["2026-08-21"]["frozen_input_identities"]
    assert "event_context" not in registry["completed_sessions"]["2026-08-21"]["frozen_input_identities"]
    resolve_opportunity_freeze("2026-08-24")
    assert HISTORICAL_FREEZE.read_bytes() == before
    assert json.loads(HISTORICAL_FREEZE.read_text(encoding="utf-8"))["snapshot_id"] == PROTECTED_FREEZE_ID
