"""Pure construction of historical session paths; selection belongs to callers.

No root resolution, validation, discovery, directory creation or I/O. Path flavours
are inherited from the supplied root, exactly as in the legacy function.
"""
from pathlib import Path


def session_artifact_paths(root: Path, session: str, *, official_event_context_dir: str) -> dict[str, Path]:
    ops = root / "operations-review"
    nodash = session.replace("-", "")
    return {
        "exact_session_snapshot": ops / f"p3f9b-market-wide-exact-session-scaleout-{nodash}" / "p3f9b_mva_exact_session_snapshot.json",
        "p3f7_bundle": ops / f"p3f9b-market-wide-exact-session-scaleout-{nodash}" / "p3f7_mva_daily_research_bundle_exact_session.json",
        "p3f8_run": ops / f"p3f9b-market-wide-exact-session-scaleout-{nodash}" / "p3f8_mva_operational_run_exact_session.json",
        "dnse_only_exact_session_snapshot": ops / f"p3f9b-market-wide-exact-session-scaleout-{nodash}" / "dnse_only_exact_session_snapshot.json",
        "multi_source_market_evidence": ops / f"p3f9b-market-wide-exact-session-scaleout-{nodash}" / "multi_source_exact_session_market_evidence.json",
        "multi_source_recovery_abort": ops / f"p3f9b-market-wide-exact-session-scaleout-{nodash}" / "multi_source_exact_session_recovery_runtime_budget_abort.json",
        "supplemental_provider_block": ops / f"p3f9b-market-wide-exact-session-scaleout-{nodash}" / "supplemental_provider_block.json",
        "breadth_foundation": ops / f"current-market-universe-breadth-foundation-v1-{nodash}" / "current_market_universe_breadth_foundation_artifact.json",
        "universe_resolution": ops / f"current-universe-status-and-session-coverage-resolution-v1-{nodash}" / "current_universe_status_and_session_coverage_resolution_artifact.json",
        "liquidity_research": ops / f"market-wide-current-liquidity-research-v1-{nodash}" / "market_wide_current_liquidity_research_artifact.json",
        "official_liquidity": ops / f"official-exchange-liquidity-research-v1-{nodash}" / "official_exchange_liquidity_research_artifact.json",
        "technical_recovery": ops / f"market-wide-current-technical-coverage-scaleout-v1-{nodash}" / "market_wide_current_technical_coverage_recovery_artifact.json",
        "descriptive_research": ops / f"market-wide-current-descriptive-research-v1-{nodash}" / "market_wide_current_descriptive_research_artifact.json",
        "screening_foundation": ops / f"current-market-screening-opportunity-comparison-foundation-v1-{nodash}" / "current_market_screening_opportunity_comparison_foundation_artifact.json",
        "tactical_classifier": ops / f"watchlist-tactical-entry-decision-v1-{nodash}" / "watchlist_tactical_entry_classifier_artifact.json",
        "corporate_intelligence": ops / f"market-wide-current-corporate-intelligence-v1-{nodash}" / "market_wide_current_corporate_intelligence_artifact.json",
        "valuation": ops / f"market-wide-current-valuation-v1-{nodash}-session{nodash}" / "market_wide_current_valuation_artifact.json",
        "sector_leadership": ops / f"current-market-sector-leadership-context-v1-{nodash}" / "current_market_sector_leadership_context_artifact.json",
        "peer_relative": ops / f"sector-aware-relative-research-v1-{nodash}" / "sector_aware_relative_research_artifact.json",
        "scenario": ops / f"current-evidence-bound-scenario-v1-{nodash}" / "current_evidence_bound_scenario_artifact.json",
        "strategy": ops / f"polymorphic-current-strategy-classification-v1-{nodash}" / "polymorphic_current_strategy_classification_artifact.json",
        "opportunity_prioritization": ops / f"current-opportunity-prioritization-v1-{nodash}" / "current_opportunity_prioritization_artifact.json",
        "risk_register": ops / f"current-research-risk-register-v1-{nodash}" / "current_research_risk_register_artifact.json",
        "decision_packet": ops / f"current-research-decision-packet-v1-{nodash}" / "current_research_decision_packet_artifact.json",
        "decision_packet_dashboard": ops / f"current-research-decision-packet-dashboard-shadow-v1-{nodash}" / "market_wide_product_validation.json",
        "technical_coverage_disposition": ops / f"same-session-technical-coverage-recovery-v1-{nodash}" / "same_session_technical_coverage_disposition_artifact.json",
        "fundamental": ops / "market-wide-current-fundamental-research-v1-20260823" / "market_wide_current_fundamental_research_artifact.json",
        "official_universe": ops / "current-official-market-universe-integration-v1-20260824" / "current_official_market_universe_artifact.json",
        "official_event_context": ops / official_event_context_dir / "current_official_event_context_artifact.json",
        "catalyst": ops / "catalyst-event-research-context-v1-20260820" / "catalyst_event_research_context_artifact.json",
        "historical_context": ops / "market-wide-historical-research-context-v1-20260824" / "market_wide_historical_research_context_artifact.json",
        "financial_momentum": ops / "current-financial-momentum-context-v1" / "current_financial_momentum_context_artifact.json",
        "corporate_event_context": ops / "current-corporate-event-context-v1" / "current_corporate_event_context_artifact.json",
        "corporate_intelligence_axis": ops / "current-corporate-intelligence-axis-v1" / "current_corporate_intelligence_axis_artifact.json",
        "session_triage": ops / f"full-universe-entry-candidate-triage-v1-{nodash}" / f"full_universe_entry_candidate_triage_{nodash}.json",
        "named_20260824_triage": ops / "full-universe-entry-candidate-triage-20260824" / "full_universe_entry_candidate_triage_20260824.json",
        "postclose_20260824_triage": ops / "full-universe-entry-candidate-triage-postclose-20260824" / "full_universe_entry_candidate_triage_20260824.json",
        "integrated_investment_decision_product": ops / f"integrated-investment-decision-product-v1-{nodash}" / "integrated_investment_decision_product_artifact.json",
        "daily_integrated_decision_brief": ops / f"daily-integrated-decision-brief-v1-{nodash}" / "daily_integrated_decision_brief_artifact.json",
        "market_structure_breakout_v3_projection": ops / f"integrated-investment-decision-product-v1-{nodash}" / "market_structure_breakout_v3_projection_artifact.json",
        "tactical_momentum_context": ops / f"integrated-investment-decision-product-v1-{nodash}" / "tactical_momentum_context_artifact.json",
        "tactical_confirmation_context": ops / f"integrated-investment-decision-product-v1-{nodash}" / "tactical_confirmation_context_artifact.json",
        "tactical_confirmation_invalidation_boundaries": ops / f"integrated-investment-decision-product-v1-{nodash}" / "tactical_confirmation_invalidation_boundaries_artifact.json",
        "technical_structure_context": ops / f"integrated-investment-decision-product-v1-{nodash}" / "technical_structure_context_artifact.json",
        "tactical_setup_tags": ops / f"integrated-investment-decision-product-v1-{nodash}" / "tactical_setup_tags_artifact.json",
        "operational_fundamental_context_integration": ops / f"integrated-investment-decision-product-v1-{nodash}" / "operational_fundamental_context_integration_artifact.json",
        "current_research_entity_applicability": ops / f"integrated-investment-decision-product-v1-{nodash}" / "current_research_entity_applicability_artifact.json",
        "financial_analysis_product": ops / f"financial-analysis-product-v2-{nodash}" / "financial_analysis_product_artifact.json",
        "current_valuation_evaluated": ops / f"financial-analysis-product-v2-{nodash}" / "current_research_valuation_context_artifact.json",
        "prospective_market_snapshot_manifest": ops / f"prospective-market-snapshot-v1-{nodash}" / "prospective_market_snapshot_manifest.json",
    }


def fixed_session_artifact_paths(root: Path, session: str) -> dict[str, Path]:
    """Fixed paths only; omit the one historical discovery-dependent event entry."""
    paths = session_artifact_paths(root, session, official_event_context_dir="current-official-event-context-integration-v1-UNAVAILABLE")
    del paths["official_event_context"]
    return paths
