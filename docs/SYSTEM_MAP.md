# Stock Lookup — System Map

> Navigation aid only. docs/STATE.md, docs/ROADMAP.md, docs/DECISIONS.md and docs/ROADMAP_STATE.json remain authority.

## Canonical Pipeline Flow

```
stocklookup.ps1
  └─> stocklookup.py
        └─> Canonical Daily Operation (canonical_daily_operation.py / daily_analysis_pipeline.py)
              ├─> Market-Data Acquisition (canonical_post_close_pipeline.py)
              ├─> Canonical / Current Research (daily_producer_pipeline.py / daily_research_session_operations.py)
              ├─> Tactical Engine V2 (tactical_behavior_context.py / watchlist_tactical_entry_classifier.py)
              ├─> Financial Analysis V2 (financial_analysis_engine_v2.py / financial_analysis_product_projection.py)
              ├─> Valuation & Opportunity Integration (current_valuation_opportunity_integration.py)
              ├─> Investment Decision Workspace (investment_decision_workspace_projection.py)
              ├─> Screener Master Projection (screener_master_projection.py)
              ├─> AI Handoff Publication (ai_handoff_publication.py / next_session_decision_brief.py)
              └─> Dashboard Release (dashboard_release_publisher.py / publish_dashboard.py)
```

## Stage Map

### 1. Host Entrypoint
- **Responsibility:** Windows PowerShell entry wrapper; locates Python interpreter and invokes `stocklookup.py`.
- **Primary Entry Module:** [`stocklookup.ps1`](../stocklookup.ps1)
- **Key Output Contract:** Process exit code and standard console output.

### 2. Owner CLI Dispatcher
- **Responsibility:** Command dispatcher for `daily` and `roadmap`; manages preflight checks, pipeline execution, decision brief generation, AI handoff, and dashboard publishing.
- **Primary Entry Module:** [`stocklookup.py`](../stocklookup.py)
- **Key Output Contract:** CLI execution status, terminal handoff summary, and process exit code.

### 3. Current Canonical Daily Operation
- **Responsibility:** Sequential post-close lifecycle: session qualification gates (Phase A/B), market-data acquisition, session input registration, daily producer execution, runtime materialization, and trusted-subset release.
- **Primary Entry Module:** [`canonical_daily_operation.py`](../canonical_daily_operation.py) (invoked via [`daily_analysis_pipeline.py`](../daily_analysis_pipeline.py) `--canonical-post-close`)
- **Key Output Contract:** `canonical_daily_operation/v1` manifest (`operations-review/canonical-post-close-v1/<session>/post-close-attempt-<ts>/canonical_daily_operation_manifest.json`).

### 4. Market-Data Acquisition
- **Responsibility:** Governed market-wide post-close EOD data capture (P3F9B route) and exact-session MVA snapshot materialization.
- **Primary Entry Module:** [`canonical_post_close_pipeline.py`](../canonical_post_close_pipeline.py) (`acquire_and_materialize`)
- **Key Output Contract:** `p3f9_exact_session_mva_snapshot/v2` (`market_wide_mva_p3f9_scaleout_artifact.json`).

### 5. Canonical / Current Research
- **Responsibility:** Deterministic multi-axis research computation across descriptive metrics, breadth, sector leadership, corporate intelligence, screening opportunities, and daily producer operations.
- **Primary Entry Module:** [`daily_producer_pipeline.py`](../daily_producer_pipeline.py) / [`daily_research_session_operations.py`](../daily_research_session_operations.py)
- **Key Output Contract:** `daily_research_session_operation/v1` (`daily_research_session_operations_artifact.json`, `ai_research_session_bundle.json`).

### 6. Tactical (Tactical and Behavioral Engine V2)
- **Responsibility:** Evaluates nine-state entry classification, close-only technical structure, multi-label setup tags, and confirmation/invalidation price boundaries.
- **Primary Entry Module:** [`tactical_behavior_context.py`](../tactical_behavior_context.py) (with [`watchlist_tactical_entry_classifier.py`](../watchlist_tactical_entry_classifier.py))
- **Key Output Contract:** `tactical_behavior_context/v1` (`tactical_behavior_context_artifact.json`).

### 7. Financial V2
- **Responsibility:** Structured financial fact extraction, period semantics resolution, layered issuer applicability classification, and working capital/liquidity ratios.
- **Primary Entry Module:** [`financial_analysis_engine_v2.py`](../financial_analysis_engine_v2.py) / [`financial_analysis_product_projection.py`](../financial_analysis_product_projection.py)
- **Key Output Contract:** `financial_analysis_product_projection/v1` (`financial_analysis_product_projection_artifact.json`).

### 8. Valuation / Opportunity Integration
- **Responsibility:** Multi-method valuation metrics, peer-relative percentiles, opportunity context join, and governed research candidate stance assignment.
- **Primary Entry Module:** [`current_valuation_opportunity_integration.py`](../current_valuation_opportunity_integration.py)
- **Key Output Contract:** `opportunity_context/v1` and `security_decision_context/v1` (`current_valuation_opportunity_integration_artifact.json`).

### 9. Investment Decision Workspace
- **Responsibility:** Multi-axis decision convergence joining Opportunity Context, Tactical V2, Financial V2, liquidity research proxy, and research stances into unified per-ticker decision records.
- **Primary Entry Module:** [`investment_decision_workspace_projection.py`](../investment_decision_workspace_projection.py)
- **Key Output Contract:** `investment_decision_workspace_dashboard_projection/v1` (`investment_decision_workspace_dashboard_projection_artifact.json`, `decision_workspace_cards.json`).

### 10. Screener Master Projection
- **Responsibility:** Presentation read-model joining the canonical screening snapshot with Decision Workspace cards, Financial V2 compact states, VCI sector labels, and tactical/liquidity fields.
- **Primary Entry Module:** [`screener_master_projection.py`](../screener_master_projection.py)
- **Key Output Contract:** `screener_master_projection/v1` (`screener_master_projection_artifact.json`, `screener_master_projection.json`).

### 11. AI Handoff
- **Responsibility:** Deterministic packaging and idempotent git publication of daily research session bundle and next-session decision brief to the private AI handoff repository.
- **Primary Entry Module:** [`ai_handoff_publication.py`](../ai_handoff_publication.py) / [`next_session_decision_brief.py`](../next_session_decision_brief.py)
- **Key Output Contract:** Git commit in private handoff repo (`LATEST.json`, `ai_research_session_bundle.json`, `next_session_decision_brief.json`).

### 12. Dashboard Release
- **Responsibility:** Atomic validation, staging, and publishing of canonical runtime artifacts and projection models to the web dashboard distribution repository.
- **Primary Entry Module:** [`dashboard_release_publisher.py`](../dashboard_release_publisher.py) / [`publish_dashboard.py`](../publish_dashboard.py)
- **Key Output Contract:** Published dashboard bundle (`decision_workspace_cards.json`, `screener_master_projection.json`, `bundle_manifest.json`).
