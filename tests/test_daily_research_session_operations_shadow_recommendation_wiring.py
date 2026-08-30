"""Focused tests for the narrow Daily Producer integration point: build_operation()'s new
optional `shadow_security_recommendation` parameter, threaded through to
current_daily_decision_research_product.build() -> attach_decision_context().

This module computes no recommendation or invalidation of its own; it proves that an
already-built same-session shadow_security_recommendation/v1 artifact (produced by
daily_session_shadow_recommendation.build(), reusing the existing engines verbatim) is
retained by the Session Bundle when supplied, and that omitting it reproduces the exact
pre-existing behavior.
"""
from __future__ import annotations

import json
from pathlib import Path

from daily_research_session_operations import build_operation, load_registry, resolve_inputs
from daily_session_shadow_recommendation import build as build_daily_session_shadow_recommendation


ROOT = Path(__file__).resolve().parents[1]
SESSION = "2026-08-21"

SHARED_PATHS = {
    "fundamental": "operations-review/fundamental-cross-sectional-scoring-and-ranking-v1-20260828/artifact.json",
    "valuation": "operations-review/current-valuation-research-proxy-and-relative-value-axis-v1-20260828/artifact.json",
    "events": "operations-review/current-corporate-event-context-v1/current_corporate_event_context_artifact.json",
    "ttm": "operations-review/financial-flow-semantics-and-ttm-bridge-foundation-v1-20260828/artifact.json",
    "risk_research": "operations-review/current-portfolio-risk-research-v1-20260829/artifact.json",
    "a1_temporal": "operations-review/a1-bitemporal-semantic-contract-v1-20260828/artifact.json",
    "a2_temporal": "operations-review/a2-provider-publication-first-seen-retention-v1-20260829/artifact.json",
}


def _load(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _resolved():
    return resolve_inputs(ROOT, SESSION, load_registry(ROOT))[0]


def _session_shadow_recommendation(inputs):
    shared = {key: _load(path) for key, path in SHARED_PATHS.items()}
    chain = build_daily_session_shadow_recommendation(
        market=inputs["descriptive"], tactical=inputs["tactical"], fundamental=shared["fundamental"],
        valuation=shared["valuation"], events=shared["events"], ttm=shared["ttm"],
        risk_research=shared["risk_research"], valuation_research=shared["valuation"],
        a1_temporal=shared["a1_temporal"], a2_temporal=shared["a2_temporal"],
    )
    return chain["shadow_security_recommendation"]


def test_missing_shadow_security_recommendation_reproduces_pre_existing_behavior():
    """No regression: omitting the new optional param is byte-identical to before it existed."""
    inputs = _resolved()
    operation = build_operation(inputs, SESSION, producer_head="producer", consumer_head="consumer")
    card = next(iter(operation["product"]["detailed_research_cards"].values()))
    assert card["recommendation"] is None
    assert card["recommendation_retention"]["status"] == "UNAVAILABLE"
    assert card["recommendation_retention"]["reason"] == "UPSTREAM_SHADOW_SECURITY_RECOMMENDATION_NOT_SUPPLIED_OR_UNVERIFIED"


def test_daily_producer_supplies_exact_session_source_identities_and_bundle_retains_them():
    inputs = _resolved()
    shadow = _session_shadow_recommendation(inputs)
    assert shadow["metadata"]["as_of_session"] == SESSION
    operation = build_operation(inputs, SESSION, producer_head="producer", consumer_head="consumer", shadow_security_recommendation=shadow)
    cards = operation["product"]["detailed_research_cards"]
    retained = [ticker for ticker, card in cards.items() if card["recommendation"] is not None]
    assert retained, "expected at least one ticker to retain a same-session recommendation"
    for ticker in retained:
        record = shadow["records"][ticker]
        assert cards[ticker]["recommendation"]["recommendation_label"] == record["recommendation"]["recommendation_label"]
        assert cards[ticker]["recommendation"]["as_of_session"] == SESSION
        assert cards[ticker]["fundamental_invalidation"]["current_trigger_state"] == record["fundamental_invalidation"]["current_trigger_state"]
        assert cards[ticker]["recommendation_retention"]["status"] == "RETAINED"
        assert cards[ticker]["fundamental_invalidation_retention"]["status"] == "RETAINED"


def test_ticker_absent_from_the_governed_recommendation_cohort_stays_explicit():
    inputs = _resolved()
    shadow = _session_shadow_recommendation(inputs)
    operation = build_operation(inputs, SESSION, producer_head="producer", consumer_head="consumer", shadow_security_recommendation=shadow)
    cards = operation["product"]["detailed_research_cards"]
    outside_cohort = [ticker for ticker in cards if ticker not in shadow["records"]]
    assert outside_cohort, "expected at least one Session Bundle ticker outside the narrower recommendation cohort"
    for ticker in outside_cohort:
        assert cards[ticker]["recommendation"] is None
        assert cards[ticker]["recommendation_retention"]["reason"] == "TICKER_NOT_IN_UPSTREAM_SHADOW_SECURITY_RECOMMENDATION"


def test_wrong_session_shadow_artifact_is_rejected_not_silently_relabeled():
    """The wiring does not bypass attach_decision_context()'s own session-coherence gate."""
    inputs_21 = _resolved()
    inputs_24 = resolve_inputs(ROOT, "2026-08-24", load_registry(ROOT))[0]
    stale_shadow = _session_shadow_recommendation(inputs_24)  # as_of_session == 2026-08-24
    operation = build_operation(inputs_21, "2026-08-21", producer_head="producer", consumer_head="consumer", shadow_security_recommendation=stale_shadow)
    cards = operation["product"]["detailed_research_cards"]
    overlapping = [ticker for ticker in cards if ticker in stale_shadow["records"]]
    assert overlapping
    for ticker in overlapping:
        assert cards[ticker]["recommendation"] is None
        assert cards[ticker]["recommendation_retention"]["reason"] == "SESSION_MISMATCH_UPSTREAM_RECOMMENDATION_NOT_SAME_SESSION"


def test_repeated_build_with_the_same_shadow_artifact_is_identity_stable():
    inputs = _resolved()
    shadow = _session_shadow_recommendation(inputs)
    first = build_operation(inputs, SESSION, producer_head="producer", consumer_head="consumer", shadow_security_recommendation=shadow)
    second = build_operation(inputs, SESSION, producer_head="producer", consumer_head="consumer", shadow_security_recommendation=shadow)
    assert first["manifest"]["operation_identity"] == second["manifest"]["operation_identity"]
    assert first["product"]["artifact_sha256"] == second["product"]["artifact_sha256"]
