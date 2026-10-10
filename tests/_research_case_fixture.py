"""Fictitious lifecycle inputs; no retained loaders, model calls or real reviews.

The fifteen-member cohort preserves the existing thirteen-member panel invariant.
Authority labels are test branches, never evidence qualification. Every draft and
later update is a fixture; tests supply durable stores beneath tmp_path.
"""
from stocklookup_core.research.evidence_gated_research_decision_workflow import build
from stocklookup_core.research.evidence_bound_ai_research_human_review import (
    build_ai_input_collection, prompt_contract,
)
from stocklookup_core.research.analyst_research_workbench import AnalystResearchWorkbench

SESSION = "2026-01-05"
TICKERS = tuple(f"FIX{index:02}" for index in range(15))


def workflow_inputs():
    names = ("eligibility", "setups", "events", "downside", "market", "scenarios",
             "mva_bundle", "official_financial_panel", "fundamental_readiness")
    artifacts = {name: {"artifact_identity": f"TEST_FIXTURE:{name}",
                        "research_session": SESSION, "records": []} for name in names}
    product = {"artifact_identity": "TEST_FIXTURE:product",
               "daily_market_research": {"session": SESSION}, "stock_research": []}
    for index, ticker in enumerate(TICKERS):
        product["stock_research"].append({
            "ticker": ticker,
            "research_summary": {
                "fundamental_authority": "OFFICIAL_QUALIFIED" if index < 13 else "PROVIDER_RESEARCH",
                "trend_state": "BELOW_MA20" if index == 0 else "ABOVE_MA20",
            },
            "ai_ready_brief": {"facts": {"session": SESSION, "fixture": True}},
        })
        lens_states = {
            "TREND_MOMENTUM_RESEARCH": "ELIGIBLE", "SCENARIO_RESEARCH": "UNAVAILABLE",
            "CATALYST_RESEARCH": "UNAVAILABLE", "LIQUIDITY_SENSITIVE_RESEARCH": "BLOCKED",
            "HISTORICAL_PIT_STRATEGY_RESEARCH": "BLOCKED",
        }
        lenses = {name: {
            "eligibility": status, "authority_ceiling": "SHADOW_ONLY",
            "reason_codes": ["TEST_FIXTURE"], "lens_identity": f"TEST_FIXTURE:{ticker}:{name}",
            "observed_input_statuses": {},
        } for name, status in lens_states.items()}
        artifacts["eligibility"]["records"].append({
            "ticker": ticker, "research_session": SESSION, "lenses": lenses,
        })
        artifacts["setups"]["records"].append({
            "ticker": ticker, "research_session": SESSION, "record_setup_state": "NO_MATCH",
            "active_setup_ids": [], "active_setup_authorities": [],
        })
        artifacts["events"]["records"].append({
            "ticker": ticker, "research_session": SESSION, "event_facts": [],
            "event_context_identity": f"TEST_FIXTURE:event:{ticker}",
        })
        artifacts["downside"]["records"].append({
            "ticker": ticker, "research_session": SESSION, "domains": {
                "TECHNICAL_DOWNSIDE_CONTEXT": {
                    "status": "OBSERVED_ADVERSE_TECHNICAL_CONTEXT" if index == 0 else "UNKNOWN",
                    "authority_tier": "SHADOW_ONLY", "reason_codes": ["TEST_FIXTURE_RISK"],
                },
            },
        })
        artifacts["mva_bundle"]["records"].append({
            "identity": {"canonical_ticker": ticker}, "session": SESSION,
            "empirical_active_cohort_member": True,
            "mva_provider_proxy_valuation": {
                "status": "MISSING", "reason": "TEST_FIXTURE_MISSING_VALUATION",
            },
        })
    artifacts["scenarios"]["scenarios"] = [{
        "ticker": TICKERS[0], "scenario_content_identity": "TEST_FIXTURE:scenario",
        "scenario_qualification_status": "PARTIAL_EVIDENCE_BOUND_SCENARIO",
        "probability_status": "UNQUALIFIED",
        "thesis_reference": {"items": [{"claim": "Synthetic supporting observation.",
                                       "authority_tier": "RESEARCH_SHADOW"}]},
        "counter_thesis_reference": {"items": [{"claim": "Synthetic contrary observation.",
                                               "authority_tier": "RESEARCH_SHADOW"}]},
    }]
    artifacts["market"]["breadth"] = {
        "trend": {"descriptor": {"descriptor": "TEST_FIXTURE_BREADTH"}},
    }
    artifacts["official_financial_panel"].update({
        "cohort_identity": {"as_of_session": SESSION},
        "before_after_comparison": {"fundamental_readiness_status": {
            "after": {"PARTIAL": 13, "BLOCKED": 2},
        }},
        "newly_qualified_issuers": [],
    })
    artifacts["fundamental_readiness"]["issuer_research_readiness"] = [{
        "issuer_identity": {"ticker": TICKERS[1], "entity_class": "banking"},
        "metrics": [{"metric_id": "fixture:corporate_metric", "status": "NOT_APPLICABLE"}],
        "metric_family_states": {"TEST_FIXTURE": "PARTIAL"},
    }]
    return {"product": product, **artifacts}


def fixture_draft(packet):
    claims = [{
        "claim_id": f"fixture-claim-{index}", "claim_type": "INFERENCE",
        "section": "COUNTER_THESIS" if item["evidence_id"] in packet["mandatory_counter_evidence_ids"] else "THESIS",
        "claim_text": "TEST_FIXTURE evidence remains bounded for research review.",
        "supporting_evidence_ids": [item["evidence_id"]], "conflicting_evidence_ids": [],
        "authority_class": item["authority"], "referenced_dimension": None,
        "numeric_evidence_ids": [],
    } for index, item in enumerate(packet["evidence"])]
    sections = {name: [] for name in prompt_contract()["required_sections"]}
    for claim in claims:
        sections[claim["section"]].append(claim["claim_id"])
    return {
        "fixture": True, "source_ai_input_identity": packet["ai_input_identity"],
        "draft_identity": "TEST_FIXTURE:draft:" + packet["ai_input_identity"],
        "claims": claims, "sections": sections,
        "dimension_interpretations": {name: item["eligibility"] for name, item in packet["analytical_eligibility"].items()},
        "human_review_required": True,
    }


T0 = "2026-01-06T09:00:00+07:00"
LATER = "2026-01-07T09:00:00+07:00"
LATER_KNOWN = "2026-01-07T10:00:00+07:00"


def fixture_workbench(*, case_store=None):
    decision = build(**workflow_inputs())
    collection = build_ai_input_collection(decision)
    return AnalystResearchWorkbench.from_artifacts(decision, collection, case_store=case_store)


def reviewed_fixture(workbench, ticker=TICKERS[0], *, review_state="NEEDS_MORE_EVIDENCE"):
    packet = workbench.build_ai_input(ticker)["ai_input"]
    draft = fixture_draft(packet)
    validation = workbench.validate_ai_draft(ticker, draft)["validation"]
    review = workbench.record_human_review(
        ticker, draft, reviewer_identity="TEST_FIXTURE:reviewer",
        review_timestamp="2026-01-06T08:55:00+07:00", review_state=review_state,
        reviewer_notes="TEST_FIXTURE review preserves all evidence gaps.",
        material_claim_edits=[{"claim_id":draft["claims"][0]["claim_id"],
                               "replacement_text":"TEST_FIXTURE human clarification."}],
    )["human_review"]
    return draft, validation, review


def create_fixture_case(workbench, ticker=TICKERS[0]):
    draft, validation, review = reviewed_fixture(workbench, ticker)
    return workbench.create_case(ticker, draft, validation, review, created_at=T0, known_at=T0)["case"]


def fixture_update_kwargs(case):
    return {"observed_at":LATER,"known_at":LATER_KNOWN,
            "source_evidence_identity":"fixture:later-evidence","evidence_kind":"TEST_FIXTURE",
            "relationships":[{"original_claim_id":case["original_claims"][0]["claim_id"],
                              "relationship":"DOES_NOT_ADDRESS","claim_outcome":"UNRESOLVED"}],
            "lifecycle_state":"ACTIVE","fixture":True}
