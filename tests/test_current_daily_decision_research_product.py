import json
from pathlib import Path

from current_daily_decision_research_product import (
    ABSENT_OWNER_FOCUS_STATUS,
    OWNER_FOCUS_TICKERS,
    WATCHLIST,
    build,
    content_identity,
    markdown,
)
from export_ai_bundle import attach_current_daily_decision_research_product
from polymorphic_current_strategy_classification import build as build_strategy
from shadow_security_recommendation import content_identity as shadow_content_identity


ROOT = Path(__file__).resolve().parents[1]
OPERATIONS = ROOT / "operations-review"


def _shadow_recommendation_artifact(as_of_session, records):
    """Minimal self-verifying shadow_security_recommendation/v1 fixture. `records` maps
    ticker -> (recommendation_label, invalidation_status, invalidation_trigger_state)."""
    base = {
        "schema_version": "1.0.0",
        "contract_version": "shadow_security_recommendation/v1",
        "metadata": {"as_of_session": as_of_session, "recommendation_vocabulary": [
            "INITIATE_RESEARCH_CANDIDATE", "ACCUMULATE_RESEARCH_CANDIDATE", "WAIT_FOR_CONFIRMATION",
            "HIGH_RISK_SPECULATION_ONLY", "AVOID_NEW_ENTRY", "INSUFFICIENT_EVIDENCE"]},
        "denominator": len(records),
        "residual": 0,
        "input_lineage": {"research_cases": "test:research_cases"},
        "records": {
            ticker: {
                "ticker": ticker,
                "recommendation": {
                    "recommendation_label": label,
                    "recommendation_readiness": "RECOMMENDATION_READY",
                    "shadow_posture": "TEST_POSTURE",
                    "shadow_readiness": "READY_SHADOW",
                    "as_of_session": as_of_session,
                    "recommendation_reason_codes": ["TEST_REASON_CODE"],
                    "research_action_state": "CURRENT_RESEARCH_STANCE",
                },
                "fundamental_invalidation": {
                    "status": inv_status,
                    "current_trigger_state": inv_trigger,
                    "reason": "Test retained boundary.",
                    "rule_identity": "TEST_RULE/v1",
                    "source_rule": "TEST_RULE/v1",
                    "boundary_type": "TEST_BOUNDARY",
                    "threshold": 0.2,
                    "baseline_value": 0.25,
                    "warnings": [],
                },
                "warnings": ["TEST_PACKET_WARNING"],
                "authority_boundaries": {"shadow_research_recommendation_only": True, "trade_execution_authority": False},
                "integrity_status": "COHERENT",
            }
            for ticker, (label, inv_status, inv_trigger) in records.items()
        },
        "validation": {},
        "authority_boundaries": {"shadow_research_recommendation_only": True},
    }
    return {**base, **shadow_content_identity(base)}


def _inputs():
    paths = {
        "descriptive": "market-wide-current-descriptive-research-v1-20260823/market_wide_current_descriptive_research_artifact.json",
        "tactical": "watchlist-tactical-entry-decision-v1-20260823/watchlist_tactical_entry_classifier_artifact.json",
        "peer_relative": "sector-aware-relative-research-v1-20260824/sector_aware_relative_research_artifact.json",
        "fundamental": "market-wide-current-fundamental-research-v1-20260823/market_wide_current_fundamental_research_artifact.json",
        "valuation": "market-wide-current-valuation-v1-20260824/market_wide_current_valuation_artifact.json",
        "scenario": "current-evidence-bound-scenario-v1-20260824/current_evidence_bound_scenario_artifact.json",
        "triage": "full-universe-entry-candidate-triage-20260824/full_universe_entry_candidate_triage_20260824.json",
        "corporate_intelligence": "market-wide-current-corporate-intelligence-v1-20260824/market_wide_current_corporate_intelligence_artifact.json",
    }
    return {name: json.loads((OPERATIONS / path).read_text(encoding="utf-8")) for name, path in paths.items()}


def test_product_is_deterministic_and_reuses_existing_cohorts():
    product = build(**_inputs())
    assert content_identity(product)["artifact_sha256"] == product["artifact_sha256"]
    assert product["market_brief"]["source_market_session"] == "2026-08-21"
    assert product["research_cohorts"]["EARLY_REVERSAL"]["count"] == 30
    assert product["research_cohorts"]["BREAKOUT_CONFIRMATION"]["count"] == 40
    assert product["high_priority_full_universe_review_set"]["count"] == 47
    assert product["aggregate_validation"]["entry_relevant_90_count"] == 90


def test_cards_preserve_tactical_peer_scenario_and_human_review_boundaries():
    product = build(**_inputs()); card = product["detailed_research_cards"]["ABB"]
    assert card["current_decision_state"]["entry_state"] == "EARLY_REVERSAL_CANDIDATE"
    assert card["current_decision_state"]["entry_action"] == "EARLY_ENTRY"
    assert card["scenario"]["probability_status"] == "UNKNOWN_UNCALIBRATED"
    assert card["current_decision_state"]["requires_human_review"] is True
    assert card["current_decision_state"]["position_sizing_status"] == "NOT_EVALUATED"
    assert all(claim["type"] in {"FACT", "INFERENCE", "DATA_GAP", "QUESTION_TO_VERIFY"} for group in card["thesis_counter_thesis"].values() for claim in group)
    assert card["corporate_intelligence_context"]["status"] == "NO_RETAINED_INTELLIGENCE"
    assert product["detailed_research_cards"]["HPG"]["corporate_intelligence_context"]["confirmed"][0]["status"] == "EXECUTED"
    assert "No retained corporate intelligence" not in product["detailed_research_cards"]["HPG"]["corporate_intelligence_context"]["what_to_verify"][0]


def test_markdown_is_a_compact_human_review_product_not_recommendation_text():
    brief = markdown(build(**_inputs()))
    assert "## Market brief" in brief and "## Detailed research cards" in brief
    assert "Candidate means human research candidate only" in brief
    assert "Human review required; no sizing or execution instruction." in brief
    assert "most likely" not in brief.lower()


def test_product_shows_deterministic_strategy_fit_without_turning_it_into_action():
    inputs = _inputs()
    strategy = build_strategy(descriptive=inputs["descriptive"], tactical=inputs["tactical"], peer_relative=inputs["peer_relative"], fundamental=inputs["fundamental"], valuation=inputs["valuation"], scenario=inputs["scenario"], corporate_intelligence=inputs["corporate_intelligence"])
    product = build(**inputs, strategy_classification=strategy)
    hpg = product["detailed_research_cards"]["HPG"]["strategy_fit"]
    assert hpg["is_actionable"] is False and hpg["source_artifact_identity"] == strategy["artifact_identity"]
    assert next(item for item in hpg["strategies"] if item["strategy_id"] == "EVENT_DRIVEN")["status"] == "ELIGIBLE"


def test_owner_focus_is_distinct_from_broader_watchlist_and_not_holdings():
    product = build(**_inputs())
    assert list(WATCHLIST) == ["EVF", "FPT", "HPG", "NVL", "PAN", "PNJ", "POW", "PVD", "QNS", "SSI", "VNM"]
    assert list(OWNER_FOCUS_TICKERS) == ["SSI", "HPG", "PAN", "EVF", "VNM", "FPT", "PVD", "NVL", "POW", "PNJ"]
    assert product["watchlist"]["tickers"] == list(WATCHLIST)
    assert "QNS" in product["watchlist"]["tickers"]
    assert "QNS" not in product["owner_focus"]["tickers"]
    assert product["watchlist"]["is_portfolio_holdings"] is False
    assert product["owner_focus"]["is_portfolio_holdings"] is False
    assert product["owner_focus"]["is_actionable"] is False
    assert product["authority_boundary"]["entry_action_is_research_label_not_execution_instruction"] is True
    assert product["authority_boundary"]["owner_focus_is_not_portfolio_holdings"] is True
    for ticker in OWNER_FOCUS_TICKERS:
        assert ticker in product["detailed_research_cards"]
        card = product["detailed_research_cards"][ticker]
        assert card["current_decision_state"]["entry_action_is_research_label_not_execution_instruction"] is True
        assert card["is_actionable"] is False


def test_absent_owner_focus_ticker_is_explicit_never_silently_dropped():
    inputs = _inputs()
    inputs["tactical"]["records"].pop("HPG", None)
    product = build(**inputs)
    card = product["detailed_research_cards"]["HPG"]
    assert card["status"] == ABSENT_OWNER_FOCUS_STATUS
    assert "HPG" in product["owner_focus"]["missing"]
    assert product["owner_focus"]["tickers"][1] == "HPG"
    assert "QNS" in product["watchlist"]["tickers"]


def test_opt_in_attach_passes_card_from_single_product_artifact():
    path = OPERATIONS / "current-daily-decision-research-product-v2-20260824/current_daily_decision_research_product_artifact.json"
    bundle = {"ABB": {}}
    attach_current_daily_decision_research_product(bundle, True, str(path))
    card = bundle["ABB"]["current_daily_decision_research"]
    assert card["source_artifact_identity"].startswith("current_daily_decision_research_product:")
    assert card["current_decision_state"]["entry_action"] == "EARLY_ENTRY"


def test_schema_version_bumped_additively_for_new_decision_context_fields():
    product = build(**_inputs())
    assert product["schema_version"] == "2.2.0"
    assert product["contract_version"] == "current_daily_decision_research_product/v2"


def test_recommendation_and_invalidation_absent_when_no_upstream_supplied():
    product = build(**_inputs())
    card = product["detailed_research_cards"]["HPG"]
    assert card["recommendation"] is None
    assert card["recommendation_retention"]["status"] == "UNAVAILABLE"
    assert card["recommendation_retention"]["reason"] == "UPSTREAM_SHADOW_SECURITY_RECOMMENDATION_NOT_SUPPLIED_OR_UNVERIFIED"
    assert card["fundamental_invalidation"] is None
    assert card["fundamental_invalidation_retention"]["status"] == "UNAVAILABLE"
    assert card["fundamental_invalidation_retention"]["reason"] == "UPSTREAM_SHADOW_SECURITY_RECOMMENDATION_NOT_SUPPLIED_OR_UNVERIFIED"


def test_recommendation_retained_verbatim_same_session():
    shadow = _shadow_recommendation_artifact("2026-08-21", {"HPG": ("ACCUMULATE_RESEARCH_CANDIDATE", "READY", "NOT_TRIGGERED")})
    product = build(**_inputs(), shadow_security_recommendation=shadow)
    card = product["detailed_research_cards"]["HPG"]
    rec = card["recommendation"]
    assert rec["recommendation_label"] == "ACCUMULATE_RESEARCH_CANDIDATE"
    assert rec["as_of_session"] == "2026-08-21"
    assert rec["recommendation_reason_codes"] == ["TEST_REASON_CODE"]
    assert rec["warnings"] == ["TEST_PACKET_WARNING"]
    assert rec["authority_boundaries"]["trade_execution_authority"] is False
    assert rec["source_artifact_identity"] == shadow["artifact_identity"]
    assert card["recommendation_retention"] == {
        "status": "RETAINED", "reason": None, "source_artifact_identity": shadow["artifact_identity"],
        "target_session": "2026-08-21", "source_as_of_session": "2026-08-21",
    }


def test_fundamental_invalidation_retained_with_activation_state_preserved():
    shadow = _shadow_recommendation_artifact("2026-08-21", {"HPG": ("WAIT_FOR_CONFIRMATION", "READY", "TRIGGERED")})
    product = build(**_inputs(), shadow_security_recommendation=shadow)
    inv = product["detailed_research_cards"]["HPG"]["fundamental_invalidation"]
    assert inv["status"] == "READY"
    assert inv["current_trigger_state"] == "TRIGGERED"
    assert inv["reason"] == "Test retained boundary."
    assert inv["rule_identity"] == "TEST_RULE/v1"
    assert inv["source_artifact_identity"] == shadow["artifact_identity"]


def test_non_activated_invalidation_state_preserved_exactly():
    shadow = _shadow_recommendation_artifact("2026-08-21", {"HPG": ("WAIT_FOR_CONFIRMATION", "CONDITIONAL", "UNKNOWN")})
    product = build(**_inputs(), shadow_security_recommendation=shadow)
    inv = product["detailed_research_cards"]["HPG"]["fundamental_invalidation"]
    assert inv["status"] == "CONDITIONAL"
    assert inv["current_trigger_state"] == "UNKNOWN"


def test_session_mismatch_is_rejected_never_silently_relabeled():
    shadow = _shadow_recommendation_artifact("2026-08-20", {"HPG": ("ACCUMULATE_RESEARCH_CANDIDATE", "READY", "NOT_TRIGGERED")})
    product = build(**_inputs(), shadow_security_recommendation=shadow)
    card = product["detailed_research_cards"]["HPG"]
    assert card["recommendation"] is None
    assert card["recommendation_retention"]["status"] == "UNAVAILABLE"
    assert card["recommendation_retention"]["reason"] == "SESSION_MISMATCH_UPSTREAM_RECOMMENDATION_NOT_SAME_SESSION"
    assert card["recommendation_retention"]["source_as_of_session"] == "2026-08-20"
    assert card["fundamental_invalidation"] is None
    assert card["fundamental_invalidation_retention"]["reason"] == "SESSION_MISMATCH_UPSTREAM_FUNDAMENTAL_INVALIDATION_NOT_SAME_SESSION"


def test_ticker_absent_from_upstream_is_rejected_explicitly():
    shadow = _shadow_recommendation_artifact("2026-08-21", {"SSI": ("ACCUMULATE_RESEARCH_CANDIDATE", "READY", "NOT_TRIGGERED")})
    product = build(**_inputs(), shadow_security_recommendation=shadow)
    card = product["detailed_research_cards"]["HPG"]
    assert card["recommendation"] is None
    assert card["recommendation_retention"]["reason"] == "TICKER_NOT_IN_UPSTREAM_SHADOW_SECURITY_RECOMMENDATION"
    assert product["detailed_research_cards"]["SSI"]["recommendation"]["recommendation_label"] == "ACCUMULATE_RESEARCH_CANDIDATE"


def test_tampered_upstream_artifact_fails_closed():
    shadow = dict(_shadow_recommendation_artifact("2026-08-21", {"HPG": ("ACCUMULATE_RESEARCH_CANDIDATE", "READY", "NOT_TRIGGERED")}))
    shadow["artifact_sha256"] = "0" * 64
    product = build(**_inputs(), shadow_security_recommendation=shadow)
    card = product["detailed_research_cards"]["HPG"]
    assert card["recommendation"] is None
    assert card["recommendation_retention"]["reason"] == "UPSTREAM_SHADOW_SECURITY_RECOMMENDATION_NOT_SUPPLIED_OR_UNVERIFIED"


def test_bundle_builder_never_translates_or_invents_a_label():
    for label in ("WAIT_FOR_CONFIRMATION", "HIGH_RISK_SPECULATION_ONLY", "AVOID_NEW_ENTRY", "INSUFFICIENT_EVIDENCE"):
        shadow = _shadow_recommendation_artifact("2026-08-21", {"HPG": (label, "UNAVAILABLE", "UNKNOWN")})
        product = build(**_inputs(), shadow_security_recommendation=shadow)
        rec = product["detailed_research_cards"]["HPG"]["recommendation"]
        assert rec["recommendation_label"] == label
        assert rec["recommendation_label"] not in {"BUY", "SELL", "HOLD"}


def test_source_artifact_identity_recorded_only_when_retained():
    shadow = _shadow_recommendation_artifact("2026-08-21", {"HPG": ("ACCUMULATE_RESEARCH_CANDIDATE", "READY", "NOT_TRIGGERED")})
    with_shadow = build(**_inputs(), shadow_security_recommendation=shadow)
    without_shadow = build(**_inputs())
    assert with_shadow["source_artifact_identities"]["shadow_security_recommendation"] == shadow["artifact_identity"]
    assert "shadow_security_recommendation" not in without_shadow["source_artifact_identities"]


def test_content_identity_deterministic_with_retained_decision_context():
    shadow = _shadow_recommendation_artifact("2026-08-21", {"HPG": ("ACCUMULATE_RESEARCH_CANDIDATE", "READY", "NOT_TRIGGERED")})
    first = build(**_inputs(), shadow_security_recommendation=shadow)
    second = build(**_inputs(), shadow_security_recommendation=shadow)
    assert first["artifact_sha256"] == second["artifact_sha256"]
    assert content_identity(first)["artifact_sha256"] == first["artifact_sha256"]
